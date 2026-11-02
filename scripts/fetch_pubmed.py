#!/usr/bin/env python3
"""literature-daily 的 PubMed 增量抓取脚本（纯 Python 标准库）。

流程：读 config.json（关键词列表）→ esearch（edat 增量窗口，Most Recent 排序，取全量 ID）
→ 与 seen.json 去重 → 每关键词按 retmax 收录新文献（超出部分顺延、不写 seen）→ efetch
批量取元数据与摘要 → 解析 XML（含撤稿/勘误/预印本标记）→ 候选清单 JSON；seen 原子写回。

v0.2.0 起的逻辑变更（依据见 references/benchmarks.md、evals/iteration_notes.md）：
- retmax 不再截断 esearch，而是"每关键词每轮最多新收录篇数"：esearch 取最多 id_limit
  个 ID 先与 seen 去重再截取，已读文献不再挤占名额（v0.1.x 的"seen 饿死"缺陷）。
- 排序改用 PubMed 默认的 Most Recent（按 edat 入库时间新→旧），与 edat 窗口同口径；
  不再用 sort=pub_date（会把提前定档的 ahead-of-print 排到最前、挤掉真正新入库的条目）。
- 距上次运行超过 reldate 天时自动补窗（上限 MAX_CATCHUP 天），对齐 My NCBI 的"自上次以来"。
- 记录 esearch 的 querytranslation / errorlist / warninglist：拼错的词会被 PubMed 静默忽略，
  检索式实际被放宽，必须提示用户。
- 网络瞬断与 429/5xx 自动退避重试（最多 3 次）。
- --no-commit：只读 seen，不写回；配合 render_digest.py --commit-seen 实现"渲染成功才算已读"。

用法：
  python3 scripts/fetch_pubmed.py config.json --seen data/seen.json -o candidates.json
  python3 scripts/fetch_pubmed.py config.json --offline evals/fixtures/offline_v1 -o candidates.json
  python3 scripts/fetch_pubmed.py config.json --seen data/seen.json --no-commit -o candidates.json

限速：默认每次请求间隔 1.1s（实际约 0.9 req/s，对 NCBI 温柔）；--sleep 可调但下限 0.4s
（NCBI 无 key 限速 3 req/s，0.4s 是不封 IP 的底线）。--api-key 只从命令行或环境变量
PUBMED_API_KEY 读取，绝不写入仓库。

退出码：0 成功；2 输入文件不存在；3 配置/夹具格式错误；4 网络错误。
"""

from __future__ import annotations

import email.utils
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
DEFAULT_ID_LIMIT = 1000  # esearch 每关键词最多扫描的 ID 数（只取 ID，开销很小）
MAX_ID_LIMIT = 10000
MAX_CATCHUP = 60         # 自动补窗上限（天）
RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_BACKOFF = (2.0, 5.0)  # 两次重试的等待秒数（429 若带 Retry-After 取较大者）

# PubMed 出版类型 → 日报标记（类型名以 PubMed Help 2026-11 为准；旧名一并兼容）
NOTICE_TYPES = {"Retraction Notice", "Retraction of Publication", "Published Erratum",
                "Expression of Concern"}
OPINION_TYPES = {"Comment", "Editorial", "Letter", "News", "Newspaper Article"}

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
    for field, default in (("retmax", 15), ("reldate", 7), ("id_limit", DEFAULT_ID_LIMIT)):
        value = config.get(field, default)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise InputError(f"{field} 必须是正整数，当前为 {value!r}")
    if config.get("id_limit", DEFAULT_ID_LIMIT) > MAX_ID_LIMIT:
        raise InputError(f"id_limit 不能超过 {MAX_ID_LIMIT}（esearch 单次上限）")
    if not isinstance(config.get("auto_catchup", True), bool):
        raise InputError("auto_catchup 必须是 true/false")
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
        attempts = len(RETRY_BACKOFF) + 1
        for attempt in range(attempts):
            wait = self.sleep - (time.monotonic() - self._last_at)
            if wait > 0:
                time.sleep(wait)
            try:
                with urllib.request.urlopen(url, timeout=30) as resp:
                    body = resp.read()
            except urllib.error.HTTPError as exc:
                self._last_at = time.monotonic()
                self.requests += 1
                if exc.code in RETRY_STATUS and attempt < attempts - 1:
                    delay = max(RETRY_BACKOFF[attempt], retry_after_seconds(exc))
                    print(f"[retry] {endpoint} HTTP {exc.code}，{delay:.0f}s 后重试"
                          f"（{attempt + 1}/{attempts - 1}）", file=sys.stderr)
                    time.sleep(delay)
                    continue
                print(f"[error] 请求失败（{endpoint}）：HTTP {exc.code}", file=sys.stderr)
                raise SystemExit(4) from exc
            except (urllib.error.URLError, OSError) as exc:
                self._last_at = time.monotonic()
                self.requests += 1
                if attempt < attempts - 1:
                    delay = RETRY_BACKOFF[attempt]
                    print(f"[retry] {endpoint} 网络错误（{exc}），{delay:.0f}s 后重试"
                          f"（{attempt + 1}/{attempts - 1}）", file=sys.stderr)
                    time.sleep(delay)
                    continue
                print(f"[error] 请求失败（{endpoint}）：{exc}", file=sys.stderr)
                raise SystemExit(4) from exc
            self._last_at = time.monotonic()
            self.requests += 1
            return body
        raise SystemExit(4)  # pragma: no cover（循环内必然 return 或退出）


def retry_after_seconds(exc: urllib.error.HTTPError) -> float:
    """解析 Retry-After（秒数或 HTTP 日期），无法解析返回 0。"""
    value = (exc.headers.get("Retry-After") if exc.headers else None) or ""
    value = value.strip()
    if not value:
        return 0.0
    if value.isdigit():
        return min(float(value), 60.0)
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return max(0.0, min(60.0, parsed.timestamp() - time.time()))
    except (TypeError, ValueError):
        return 0.0


def esearch_keyword(client: HttpClient, keyword: str, id_limit: int, reldate: int,
                    offline_file: str) -> dict:
    """esearch 一个关键词：edat 增量窗口，返回 {count, pmids, translation, warnings}。

    不传 sort：PubMed 的 esearch 默认即 Most Recent（按入库时间新→旧，2026-11-02 实测
    与 PubMed Help "Most Recent = date added to PubMed" 一致），与 edat 窗口同口径。
    retmax 用 id_limit 取足 ID，去重与截取在本地做。
    """
    params = {
        "db": "pubmed",
        "term": keyword,
        "datetype": "edat",
        "reldate": str(reldate),
        "retmax": str(id_limit),
        "retmode": "json",
    }
    body = client.get("esearch", params, offline_file=offline_file)
    try:
        data = json.loads(body.decode("utf-8"))
        if isinstance(data, dict) and "esearchresult" not in data and data.get("error"):
            raise InputError(f"esearch 返回错误（{keyword}）：{data['error']}")
        data = data["esearchresult"]
        if data.get("ERROR"):
            raise InputError(f"esearch 返回错误（{keyword}）：{data['ERROR']}")
        count = int(data["count"])
        pmids = [str(p) for p in data["idlist"]]
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        raise InputError(f"esearch 响应解析失败（{keyword}）：{exc}") from exc
    return {"keyword": keyword, "count": count, "pmids": pmids,
            "translation": str(data.get("querytranslation") or ""),
            "warnings": query_warnings(data)}


def query_warnings(data: dict) -> list[str]:
    """把 esearch 的 errorlist/warninglist 翻成人话。

    PubMed 对找不到的词（如拼写错误 "biomarkr"）会静默丢弃、对找不到的引号短语会
    拆开检索，检索式实际被放宽——2026-11-02 实测 "sepsis biomarkr" 退化为只搜 sepsis。
    """
    messages: list[str] = []
    errors = data.get("errorlist") or {}
    warns = data.get("warninglist") or {}
    if isinstance(errors, dict):
        for term in errors.get("phrasesnotfound") or []:
            messages.append(f"词“{term}”在 PubMed 中不存在，已被忽略（检查拼写）")
        for field in errors.get("fieldsnotfound") or []:
            messages.append(f"字段标签“{field}”无效，已被忽略")
    if isinstance(warns, dict):
        for phrase in warns.get("quotedphrasesnotfound") or []:
            messages.append(f"引号短语 {phrase} 未找到，PubMed 已拆词检索（结果可能变宽）")
        for phrase in warns.get("phrasesignored") or []:
            messages.append(f"停用词/短语“{phrase}”被忽略")
        for msg in warns.get("outputmessages") or []:
            if msg in {"NOT", "AND", "OR"}:
                # 2026-11-02 实测："sepsis AND NOT preprint[pt]" 的 NOT 被丢弃，实际只检索预印本
                messages.append(f"布尔运算符 {msg} 被 PubMed 忽略，检索式语义可能已反转"
                                f"（排除请写 “A NOT B”，不要写 “A AND NOT B”）")
            elif msg and msg != "No items found.":
                messages.append(f"PubMed 提示：{msg}")
    return messages


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
    ref_types = {n.get("RefType") or "" for n in article_node.findall(
        "MedlineCitation/CommentsCorrectionsList/CommentsCorrections")}

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
        "flags": classify_flags(pubtypes, ref_types),
        "abstract": abstract,
    }


def classify_flags(pubtypes: list[str], ref_types: set[str] | None = None) -> list[str]:
    """出版类型与更正关系 → 日报标记（排序固定，便于确定性比对）。

    - retracted：本文已撤稿（pt=Retracted Publication 或 CommentsCorrections RetractionIn）
    - concern：本文被发了关注声明（ExpressionOfConcernIn）
    - notice：本条是撤稿声明/勘误/关注声明本身（不是研究论文）
    - preprint：预印本，未经同行评审
    - opinion：述评/通讯/评论类
    - book：图书章节
    """
    types = set(pubtypes)
    refs = ref_types or set()
    flags = []
    if "Retracted Publication" in types or "RetractionIn" in refs:
        flags.append("retracted")
    if "ExpressionOfConcernIn" in refs:
        flags.append("concern")
    if types & NOTICE_TYPES:
        flags.append("notice")
    if "Preprint" in types:
        flags.append("preprint")
    if types & OPINION_TYPES:
        flags.append("opinion")
    if "Book" in types:
        flags.append("book")
    return flags


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
        "flags": ["book"],
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


def load_seen_state(path: Path) -> tuple[list[str], str | None]:
    """返回 (pmids, updated)。updated 为上次写回日期（YYYY-MM-DD），用于自动补窗。"""
    pmids = load_seen(path)
    updated = None
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("updated"), str):
            updated = data["updated"]
    return pmids, updated


def effective_reldate(reldate: int, run_date: str, last_run: str | None,
                      auto_catchup: bool = True) -> tuple[int, int | None]:
    """自上次运行以来的窗口：返回 (实际 reldate, 距上次天数)。

    My NCBI 的 What's New 记住"上次取新"的时间；PubMed Help 也建议用入库日期找
    "自上次检索以来新增"。本脚本固定 reldate 为下限，距上次 > reldate 天时补到
    gap+1 天（多 1 天重叠，由 seen 去重兜底），上限 MAX_CATCHUP。
    """
    if not last_run:
        return reldate, None
    try:
        gap = (date.fromisoformat(run_date) - date.fromisoformat(last_run)).days
    except ValueError:
        return reldate, None
    if auto_catchup and gap + 1 > reldate:
        return min(gap + 1, max(MAX_CATCHUP, reldate)), gap
    return reldate, gap


def select_new(esearch_results: list[dict], seen_set: set[str], per_keyword: int
               ) -> tuple[list[str], list[str], dict[str, dict]]:
    """先去重再截取：每关键词按 Most Recent 顺序最多收录 per_keyword 篇新文献。

    返回 (收录 PMID 有序列表, 顺延 PMID 列表, 每关键词统计)。已被前面关键词收录的
    条目不重复占名额；顺延的条目不写入 seen，下一轮仍在窗口内就会再出现。
    """
    taken: list[str] = []
    taken_set: set[str] = set()
    per_kw: dict[str, dict] = {}
    all_new: list[str] = []
    all_new_set: set[str] = set()
    for result in esearch_results:
        fresh = [p for p in dict.fromkeys(result["pmids"]) if p not in seen_set]
        for pmid in fresh:
            if pmid not in all_new_set:
                all_new.append(pmid)
                all_new_set.add(pmid)
        took = 0
        for pmid in fresh:
            if pmid in taken_set:
                continue
            if took >= per_keyword:
                break
            taken.append(pmid)
            taken_set.add(pmid)
            took += 1
        per_kw[result["keyword"]] = {"new": len(fresh), "taken": took}
    deferred = [p for p in all_new if p not in taken_set]
    return taken, deferred, per_kw


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
          api_key: str, strip_abstract: bool, commit_seen: bool = True) -> int:
    config = load_config(config_path)
    keywords = [k.strip() for k in config["keywords"]]
    retmax, base_reldate = config["retmax"], config["reldate"]
    id_limit = config.get("id_limit", DEFAULT_ID_LIMIT)
    client = HttpClient(sleep_seconds, offline_dir,
                        tool=config.get("tool", "literature-daily"),
                        email=config.get("email", ""),
                        api_key=api_key or os.environ.get("PUBMED_API_KEY", ""))

    seen, last_run = load_seen_state(seen_path) if seen_path else ([], None)
    seen_set = set(seen)
    reldate, gap = effective_reldate(base_reldate, run_date, last_run,
                                     config.get("auto_catchup", True))

    mode = f"离线夹具 {offline_dir}" if offline_dir else f"PubMed（间隔 {client.sleep:.1f}s）"
    print(f"[fetch] 关键词 {len(keywords)} 个 · reldate={reldate} 天 · 每词最多收录 {retmax} 篇新文献"
          f" · {mode}")
    if reldate != base_reldate:
        print(f"[window] 距上次运行 {gap} 天 > reldate {base_reldate}，已自动补窗到 {reldate} 天"
              f"（上限 {MAX_CATCHUP}）")

    esearch_results = []
    for index, keyword in enumerate(keywords, start=1):
        result = esearch_keyword(client, keyword, id_limit, reldate,
                                 offline_file=f"esearch_kw{index}.json")
        esearch_results.append(result)
        print(f"[esearch] “{keyword}” → 近 {reldate} 天命中 {result['count']}，扫描 ID {len(result['pmids'])}")
        sys.stdout.flush()
        for warning in result["warnings"]:
            print(f"[warn] “{keyword}”：{warning}", file=sys.stderr)
        if result["count"] > len(result["pmids"]) and len(result["pmids"]) >= id_limit:
            print(f"[warn] “{keyword}” 命中 {result['count']} 超过 id_limit {id_limit}，"
                  "只与最近入库的部分去重；建议收窄检索式", file=sys.stderr)

    union = list(dict.fromkeys(p for r in esearch_results for p in r["pmids"]))
    taken, deferred, per_kw = select_new(esearch_results, seen_set, retmax)
    new_total = len(taken) + len(deferred)
    already_seen = len(union) - new_total
    print(f"[dedup] 窗口内去重后 {len(union)} 篇 · 已看过跳过 {already_seen} 篇 · 新文献 {new_total} 篇"
          f" · 本轮收录 {len(taken)} 篇" + (f" · 顺延 {len(deferred)} 篇（超出每词上限 {retmax}，不写 seen）"
                                         if deferred else ""))

    articles = efetch_articles(client, taken, offline_file="efetch_v1.xml") if taken else {}
    if taken:
        print(f"[efetch] 取回 {len(articles)} 篇元数据与摘要")

    taken_set = set(taken)
    candidates = []
    for pmid in taken:
        article = articles[pmid]
        if strip_abstract and article["abstract"]:
            article = {**article, "abstract": None, "abstract_redacted": True}
        article["matched_keywords"] = [r["keyword"] for r in esearch_results
                                       if pmid in r["pmids"]]
        candidates.append(article)
    flagged = sum(1 for c in candidates if c.get("flags"))
    if flagged:
        print(f"[flags] {flagged} 篇带标记（撤稿/勘误/预印本/述评/图书等），渲染时显示徽标")

    payload = {
        "schema_version": "1.1",
        "tool": "literature-daily",
        "run_date": run_date,
        "offline": offline_dir is not None,
        "window": {"datetype": "edat", "reldate": reldate, "base_reldate": base_reldate,
                   "last_run": last_run, "sort": "most_recent",
                   "retmax": retmax, "id_limit": id_limit},
        "research_interests": config.get("research_interests", ""),
        "keywords": [{"keyword": r["keyword"], "count": r["count"],
                      "returned": sum(1 for p in r["pmids"] if p in taken_set),
                      "scanned": len(r["pmids"]),
                      "new": per_kw[r["keyword"]]["new"],
                      "query_translation": r["translation"],
                      "warnings": r["warnings"]} for r in esearch_results],
        "stats": {
            "esearch_hits": sum(r["count"] for r in esearch_results),
            "union": len(union),
            "already_seen": already_seen,
            "new": len(taken),
            "deferred": len(deferred),
            "requests": client.requests,
        },
        "deferred_pmids": deferred,
        "candidates": candidates,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        print(f"[done] 候选清单 → {output_path}")
    else:
        sys.stdout.write(rendered)

    if seen_path is not None and commit_seen:
        merged = sorted(set(seen).union(taken_set))  # 只写本轮收录的；顺延的下轮再来
        write_seen_atomic(seen_path, merged, run_date)
        print(f"[done] seen 已原子写回 → {seen_path}（累计 {len(merged)} 篇）")
    elif seen_path is not None:
        print(f"[done] --no-commit：seen 未改动；渲染成功后用 render_digest.py --commit-seen 标记已读")
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
                     strip_abstract=flag("--strip-abstract"),
                     commit_seen=not flag("--no-commit"))
    except InputError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
