#!/usr/bin/env python3
"""literature-daily 的 PubMed 增量抓取脚本（纯 Python 标准库）。

流程：读 config.json（关键词列表）→ esearch（edat 增量窗口）→ 与 seen.json 去重
→ efetch 批量取元数据与摘要 → 解析 XML → 候选清单 JSON；seen 原子写回（tmp + rename）。

用法：
  python3 scripts/fetch_pubmed.py config.json --seen data/seen.json -o candidates.json
  python3 scripts/fetch_pubmed.py config.json --offline evals/fixtures/offline_v1 -o candidates.json

限速：默认每次请求间隔 1.1s（实际约 0.9 req/s，对 NCBI 温柔）；--sleep 可调但下限 0.4s
（NCBI 无 key 限速 3 req/s，0.4s 是不封 IP 的底线）。--api-key 只从命令行或环境变量
PUBMED_API_KEY 读取，绝不写入仓库。

退出码：0 成功；2 输入文件不存在；3 配置/夹具格式错误；4 网络错误。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MIN_SLEEP = 0.4          # NCBI 无 key 3 req/s 的硬下限
DEFAULT_SLEEP = 1.1      # 默认更温柔：实际 ≤1 req/s
BATCH_SIZE = 100         # efetch 单批 PMID 上限

CONFIG_SCHEMA_NOTE = (
    "config.json 需要形如 {\"keywords\": [\"...\"], \"retmax\": 15, \"reldate\": 7, "
    "\"research_interests\": \"...\", \"email\": \"...\"}"
)


class InputError(Exception):
    """退出码 3：配置或夹具格式错误。"""


def load_config(path: Path) -> dict:
    if not path.is_file():
        print(f"[error] 配置文件不存在：{path}", file=sys.stderr)
        raise SystemExit(2)
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputError(f"配置不是合法 JSON：{exc}") from exc
    if not isinstance(config, dict):
        raise InputError("配置顶层必须是 JSON 对象")
    keywords = config.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        raise InputError("配置缺少非空的 keywords 列表（" + CONFIG_SCHEMA_NOTE + "）")
    if not all(isinstance(k, str) and k.strip() for k in keywords):
        raise InputError("keywords 必须是非空字符串列表")
    for field, default in (("retmax", 15), ("reldate", 7)):
        value = config.get(field, default)
        if not isinstance(value, int) or value <= 0:
            raise InputError(f"{field} 必须是正整数，当前为 {value!r}")
    return config


class HttpClient:
    """带限速的 GET；offline 模式下从夹具目录取响应。"""

    def __init__(self, sleep_seconds: float, offline_dir: Path | None,
                 tool: str, email: str, api_key: str = ""):
        self.sleep = max(MIN_SLEEP, sleep_seconds)
        self.offline_dir = offline_dir
        self.tool = tool
        self.email = email
        self.api_key = api_key
        self.requests = 0
        self._last_at = 0.0

    def get(self, endpoint: str, params: dict, offline_file: str | None = None) -> bytes:
        if self.offline_dir is not None:
            path = self.offline_dir / (offline_file or "")
            if not path.is_file():
                raise InputError(f"离线夹具缺失：{path}")
            self.requests += 1
            return path.read_bytes()
        query = dict(params)
        query["tool"] = self.tool
        if self.email:
            query["email"] = self.email
        if self.api_key:
            query["api_key"] = self.api_key
        url = f"{EUTILS}/{endpoint}.fcgi?{urllib.parse.urlencode(query)}"
        wait = self.sleep - (time.monotonic() - self._last_at)
        if wait > 0:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                body = resp.read()
        except (urllib.error.URLError, OSError) as exc:
            print(f"[error] 请求失败（{endpoint}）：{exc}", file=sys.stderr)
            raise SystemExit(4) from exc
        self._last_at = time.monotonic()
        self.requests += 1
        return body


def esearch_keyword(client: HttpClient, keyword: str, retmax: int, reldate: int,
                    offline_file: str) -> dict:
    """esearch 一个关键词：edat 增量窗口 + pub_date 排序，返回 {count, pmids}。"""
    params = {
        "db": "pubmed",
        "term": keyword,
        "datetype": "edat",
        "reldate": str(reldate),
        "retmax": str(retmax),
        "sort": "pub_date",
        "retmode": "json",
    }
    body = client.get("esearch", params, offline_file=offline_file)
    try:
        data = json.loads(body.decode("utf-8"))["esearchresult"]
        count = int(data["count"])
        pmids = [str(p) for p in data["idlist"]]
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        raise InputError(f"esearch 响应解析失败（{keyword}）：{exc}") from exc
    return {"keyword": keyword, "count": count, "pmids": pmids}


def parse_author(node: ET.Element) -> str | None:
    """作者名：个人名拼 'ForeName LastName, Suffix'；集体作者用 CollectiveName。"""
    collective = element_text(node.find("CollectiveName"))
    if collective:
        return collective
    last = (node.findtext("LastName") or "").strip()
    fore = (node.findtext("ForeName") or "").strip()
    suffix = (node.findtext("Suffix") or "").strip()
    if not last and not fore:
        return None
    name = " ".join(part for part in (fore, last) if part)
    if suffix:
        name = f"{name}, {suffix}"
    return name or None


def element_text(node: ET.Element | None) -> str:
    """取元素全文（含 <i> 等混合标记），并折叠空白。"""
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())


def parse_article(article_node: ET.Element, pmid: str) -> dict:
    """从 PubmedArticle 节点抽取日报所需字段（全部自己的解析，无第三方依赖）。

    注意真实 PubMed XML 的层级：<PubmedArticle><MedlineCitation><Article>…，
    Article 不是 PubmedArticle 的直接子节点。
    """
    title = element_text(article_node.find("MedlineCitation/Article/ArticleTitle"))
    journal_full = element_text(article_node.find("MedlineCitation/Article/Journal/Title"))
    journal_iso = element_text(
        article_node.find("MedlineCitation/Article/Journal/ISOAbbreviation"))

    pub_node = article_node.find("MedlineCitation/Article/Journal/JournalIssue/PubDate")
    medline_date = (article_node.findtext(
        "MedlineCitation/Article/Journal/JournalIssue/PubDate/MedlineDate") or "").strip()
    if pub_node is not None and (pub_node.findtext("Year") or medline_date):
        year = (pub_node.findtext("Year") or "").strip()
        month = (pub_node.findtext("Month") or "").strip()
        day = (pub_node.findtext("Day") or "").strip()
        pubdate = " ".join(part for part in (year, month, day) if part) or medline_date
    else:
        pubdate = medline_date

    abstract_parts = []
    for node in article_node.findall("MedlineCitation/Article/Abstract/AbstractText"):
        label = (node.get("Label") or "").strip()
        text = element_text(node)
        if text:
            abstract_parts.append(f"{label}: {text}" if label else text)
    abstract = " ".join(abstract_parts) if abstract_parts else None

    authors = []
    author_list = article_node.find("MedlineCitation/Article/AuthorList")
    for node in author_list.findall("Author") if author_list is not None else []:
        name = parse_author(node)
        if name:
            authors.append(name)
    # 兼容集体作者直接挂在 AuthorList 下的旧格式
    if not authors and author_list is not None:
        collective = element_text(author_list.find("CollectiveName"))
        if collective:
            authors.append(collective)

    doi = None
    for node in article_node.findall("PubmedData/ArticleIdList/ArticleId"):
        if node.get("IdType") == "doi" and (node.text or "").strip():
            doi = node.text.strip()
            break
    if doi is None:
        eloc = article_node.find("MedlineCitation/Article/ELocationID")
        if eloc is not None and eloc.get("EIdType") == "doi" and (eloc.text or "").strip():
            doi = eloc.text.strip()

    pubtypes = ["".join(n.itertext()).strip()
                for n in article_node.findall(
                    "MedlineCitation/Article/PublicationTypeList/PublicationType")
                if "".join(n.itertext()).strip()]

    return {
        "pmid": pmid,
        "title": title,
        "authors": authors,
        "journal": journal_full or journal_iso,
        "journal_iso": journal_iso,
        "pubdate": pubdate,
        "doi": doi,
        "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "pubtypes": pubtypes,
        "abstract": abstract,
    }


def parse_book_article(node: ET.Element, pmid: str) -> dict:
    """PubMed 图书条目（如 StatPearls 章节）：esearch 会命中，efetch 以
    PubmedBookArticle 返回。映射为与期刊文章相同的字段结构，pubtypes 标记为
    ["Book"]，交由 Agent 分档（通常不入必读）。"""
    book_node = node.find("BookDocument")
    title = element_text(book_node.find("ArticleTitle")) if book_node is not None else ""
    # 注意 <Book> 位于 <BookDocument> 内部（与真实 StatPearls 响应一致）
    book_title = element_text(book_node.find("Book/BookTitle")) if book_node is not None else ""
    publisher = element_text(book_node.find("Book/Publisher/PublisherName")) if book_node is not None else ""

    abstract_parts = []
    if book_node is not None:
        for abs_node in book_node.findall("Abstract/AbstractText"):
            label = (abs_node.get("Label") or "").strip()
            text = element_text(abs_node)
            if text:
                abstract_parts.append(f"{label}: {text}" if label else text)

    authors = []
    if book_node is not None:
        for author_node in book_node.findall("AuthorList/Author"):
            name = parse_author(author_node)
            if name:
                authors.append(name)

    doi = None
    if book_node is not None:
        for article_id in book_node.findall("ArticleIdList/ArticleId"):
            if article_id.get("IdType") == "doi" and (article_id.text or "").strip():
                doi = article_id.text.strip()
                break

    pub_node = book_node.find("Book/PubDate") if book_node is not None else None
    pubdate = element_text(pub_node)
    return {
        "pmid": pmid,
        "title": title,
        "authors": authors,
        "journal": book_title or publisher or "图书条目",
        "journal_iso": book_title,
        "pubdate": pubdate,
        "doi": doi,
        "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "pubtypes": ["Book"],
        "abstract": " ".join(abstract_parts) if abstract_parts else None,
    }


def efetch_articles(client: HttpClient, pmids: list[str], offline_file: str) -> dict[str, dict]:
    """efetch 批量取 PubMedXML；返回 {pmid: 解析后的字段}。

    同时处理期刊文章（PubmedArticle）与图书章节（PubmedBookArticle）——
    esearch on db=pubmed 会命中 StatPearls 等图书条目（真实运行发现的回归）。
    """
    articles: dict[str, dict] = {}
    for start in range(0, len(pmids), BATCH_SIZE):
        batch = pmids[start:start + BATCH_SIZE]
        params = {"db": "pubmed", "id": ",".join(batch),
                  "rettype": "abstract", "retmode": "xml"}
        body = client.get("efetch", params, offline_file=offline_file)
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise InputError(f"efetch 返回的不是合法 XML：{exc}") from exc
        found = set()
        for kind, parser in (("PubmedArticle", parse_article),
                             ("PubmedBookArticle", parse_book_article)):
            for node in root.findall(kind):
                pmid_node = node.find("MedlineCitation/PMID")
                if pmid_node is None:
                    pmid_node = node.find("BookDocument/PMID")
                pmid = (pmid_node.text or "").strip() if pmid_node is not None else ""
                if not pmid:
                    continue
                articles[pmid] = parser(node, pmid)
                found.add(pmid)
        missing = [p for p in batch if p not in found]
        if missing:
            raise InputError(f"efetch 结果缺少 PMID：{', '.join(missing)}")
    return articles


def load_seen(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputError(f"seen 文件不是合法 JSON：{exc}") from exc
    pmids = data.get("pmids") if isinstance(data, dict) else data
    if not isinstance(pmids, list) or not all(isinstance(p, str) for p in pmids):
        raise InputError("seen 文件格式应为 {\"pmids\": [\"...\"]}")
    return pmids


def write_seen_atomic(path: Path, pmids: list[str], run_date: str) -> None:
    """原子写回：先写 tmp 再 rename，中断不会留下半截 seen。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "updated": run_date, "pmids": sorted(pmids)}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def fetch(config_path: Path, seen_path: Path | None, output_path: Path | None,
          offline_dir: Path | None, run_date: str, sleep_seconds: float,
          api_key: str, strip_abstract: bool) -> int:
    config = load_config(config_path)
    keywords = [k.strip() for k in config["keywords"]]
    retmax, reldate = config["retmax"], config["reldate"]
    client = HttpClient(sleep_seconds, offline_dir,
                        tool=config.get("tool", "literature-daily"),
                        email=config.get("email", ""),
                        api_key=api_key or os.environ.get("PUBMED_API_KEY", ""))

    mode = f"离线夹具 {offline_dir}" if offline_dir else f"PubMed（间隔 {client.sleep:.1f}s）"
    print(f"[fetch] 关键词 {len(keywords)} 个 · reldate={reldate} 天 · retmax={retmax} · {mode}")

    esearch_results = []
    for index, keyword in enumerate(keywords, start=1):
        result = esearch_keyword(client, keyword, retmax, reldate,
                                 offline_file=f"esearch_kw{index}.json")
        esearch_results.append(result)
        print(f"[esearch] “{keyword}” → 近 {reldate} 天命中 {result['count']}，取回 {len(result['pmids'])}")

    seen = load_seen(seen_path) if seen_path else []
    seen_set = set(seen)

    union: list[str] = []
    union_set: set[str] = set()
    for result in esearch_results:
        for pmid in result["pmids"]:
            if pmid not in union_set:
                union.append(pmid)
                union_set.add(pmid)
    new_pmids = [p for p in union if p not in seen_set]
    already_seen = len(union) - len(new_pmids)
    print(f"[dedup] 本轮去重前 {len(union)} 篇 · 已看过跳过 {already_seen} 篇 · 新增 {len(new_pmids)} 篇")

    articles = efetch_articles(client, new_pmids, offline_file="efetch_v1.xml") if new_pmids else {}
    if new_pmids:
        print(f"[efetch] 取回 {len(articles)} 篇元数据与摘要")

    keyword_hits: dict[str, list[str]] = {}
    for result in esearch_results:
        keyword_hits.setdefault(result["keyword"], [])
        for pmid in result["pmids"]:
            if pmid in set(new_pmids) and pmid not in keyword_hits[result["keyword"]]:
                keyword_hits[result["keyword"]].append(pmid)

    candidates = []
    for pmid in new_pmids:
        article = articles[pmid]
        if strip_abstract and article["abstract"]:
            article = {**article, "abstract": None, "abstract_redacted": True}
        article["matched_keywords"] = [kw for kw in keywords
                                       if pmid in keyword_hits.get(kw, [])]
        candidates.append(article)

    payload = {
        "schema_version": "1.0",
        "tool": "literature-daily",
        "run_date": run_date,
        "offline": offline_dir is not None,
        "window": {"datetype": "edat", "reldate": reldate, "retmax": retmax},
        "research_interests": config.get("research_interests", ""),
        "keywords": [{"keyword": r["keyword"], "count": r["count"],
                      "returned": len(r["pmids"])} for r in esearch_results],
        "stats": {
            "esearch_hits": sum(r["count"] for r in esearch_results),
            "union": len(union),
            "already_seen": already_seen,
            "new": len(new_pmids),
            "requests": client.requests,
        },
        "candidates": candidates,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        print(f"[done] 候选清单 → {output_path}")
    else:
        sys.stdout.write(rendered)

    if seen_path is not None:
        write_seen_atomic(seen_path, seen + new_pmids, run_date)
        print(f"[done] seen 已原子写回 → {seen_path}（累计 {len(seen) + len(new_pmids)} 篇）")
    return 0


def main(args: list[str]) -> int:
    """args 不含程序名：args[0] 即配置路径（与单测调用一致）。"""
    if not args or args[0] in {"-h", "--help"}:
        print(__doc__.strip())
        return 0
    config_path = Path(args[0])

    def opt_value(name: str) -> str | None:
        return args[args.index(name) + 1] if name in args else None

    def flag(name: str) -> bool:
        return name in args

    seen = opt_value("--seen")
    output = opt_value("-o") or opt_value("--output")
    offline = opt_value("--offline")
    api_key = opt_value("--api-key") or ""
    run_date = opt_value("--date")
    sleep_seconds = float(opt_value("--sleep") or DEFAULT_SLEEP)
    if sleep_seconds < MIN_SLEEP:
        print(f"[warn] --sleep {sleep_seconds}s 低于 NCBI 安全下限，已强制为 {MIN_SLEEP}s",
              file=sys.stderr)
        sleep_seconds = MIN_SLEEP

    try:
        return fetch(config_path,
                     seen_path=Path(seen) if seen else None,
                     output_path=Path(output) if output else None,
                     offline_dir=Path(offline) if offline else None,
                     run_date=run_date or date.today().isoformat(),
                     sleep_seconds=sleep_seconds,
                     api_key=api_key,
                     strip_abstract=flag("--strip-abstract"))
    except InputError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
