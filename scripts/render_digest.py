#!/usr/bin/env python3
"""literature-daily 的日报渲染脚本：把候选清单 + Agent 分档导读渲染成 markdown 日报。

用法：
  python3 scripts/render_digest.py candidates.json verdicts.json -o reports/2026-09-19.md

verdicts.json 由 Agent 产出，每篇候选一条：
  {"pmid": "...", "bucket": "must_read|worth_a_look|skip", "one_liner": "中文一句话", "reason": "..."}

防抄袭红线（落地成代码）：渲染前校验每条 one_liner 与 reason，若包含对应摘要原文
连续 ≥25 词的片段（IGNORECASE 的字母数字词序列），以退出码 4 拒绝输出，不落盘日报。

退出码：0 成功；2 输入文件不存在；3 输入格式/覆盖错误；4 导读大段复述摘要（抄袭红线）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BUCKETS = ("must_read", "worth_a_look", "skip")
BUCKET_META = {
    "must_read": ("🔴 必读（与研究方向强相关，建议点开读原文）", True),
    "worth_a_look": ("🟡 值得扫一眼（可能相关，扫标题与导读即可）", True),
    "skip": ("⚪ 可跳过（仅字面命中，不写导读）", False),
}
PLAGIARISM_N = 25          # 摘要原文连续 ≥25 词即判定为抄袭
WORD_RE = re.compile(r"[a-z0-9]+")

AUTHOR_LIMIT = 3           # 日报里最多列 3 位作者


def load_json(path: Path) -> dict:
    if not path.is_file():
        print(f"[error] 输入文件不存在：{path}", file=sys.stderr)
        raise SystemExit(2)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[error] {path} 不是合法 JSON：{exc}", file=sys.stderr)
        raise SystemExit(3) from exc
    if not isinstance(data, dict):
        print(f"[error] {path} 顶层必须是 JSON 对象", file=sys.stderr)
        raise SystemExit(3)
    return data


def word_ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    words = WORD_RE.findall(text.lower())
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def find_plagiarism(text: str, abstract: str, n: int = PLAGIARISM_N) -> str | None:
    """返回 text 中命中的 ≥n 连续词片段（供报错展示），无命中返回 None。"""
    if not abstract:
        return None
    grams = word_ngrams(abstract, n)
    words = WORD_RE.findall(text.lower())
    for i in range(len(words) - n + 1):
        gram = tuple(words[i:i + n])
        if gram in grams:
            return " ".join(gram)
    return None


def validate(candidates: dict, verdicts: dict) -> list[dict]:
    """校验覆盖度、字段与防抄袭红线；失败打印中文原因并退出。"""
    rows = candidates.get("candidates")
    if not isinstance(rows, list):
        print("[error] 候选清单缺少 candidates 列表", file=sys.stderr)
        raise SystemExit(3)
    by_pmid = {str(row.get("pmid")): row for row in rows if row.get("pmid")}
    if not by_pmid:
        print("[error] 候选清单为空或缺少 pmid 字段", file=sys.stderr)
        raise SystemExit(3)

    entries = verdicts.get("verdicts")
    if not isinstance(entries, list):
        print("[error] 导读文件缺少 verdicts 列表", file=sys.stderr)
        raise SystemExit(3)

    seen_pmids: set[str] = set()
    result: list[dict] = []
    for entry in entries:
        pmid = str(entry.get("pmid", ""))
        bucket = entry.get("bucket")
        one_liner = str(entry.get("one_liner") or "").strip()
        reason = str(entry.get("reason") or "").strip()
        if pmid not in by_pmid:
            print(f"[error] 导读里的 PMID {pmid or '(空)'} 不在候选清单中", file=sys.stderr)
            raise SystemExit(3)
        if pmid in seen_pmids:
            print(f"[error] 导读里 PMID {pmid} 重复出现", file=sys.stderr)
            raise SystemExit(3)
        seen_pmids.add(pmid)
        if bucket not in BUCKETS:
            print(f"[error] PMID {pmid} 的 bucket 必须是 {'/'.join(BUCKETS)}，当前为 {bucket!r}",
                  file=sys.stderr)
            raise SystemExit(3)
        if bucket != "skip" and not one_liner:
            print(f"[error] PMID {pmid}（{bucket}）缺少中文一句话导读 one_liner", file=sys.stderr)
            raise SystemExit(3)
        if bucket == "must_read" and not reason:
            print(f"[error] PMID {pmid}（must_read）缺少推荐理由 reason", file=sys.stderr)
            raise SystemExit(3)
        for field, text in (("one_liner", one_liner), ("reason", reason)):
            hit = find_plagiarism(text, by_pmid[pmid].get("abstract") or "")
            if hit:
                print(
                    f"[error] 防抄袭红线：PMID {pmid} 的 {field} 复述了摘要原文连续 "
                    f">{PLAGIARISM_N - 1} 词的片段（“{hit}…”），已拒绝渲染。"
                    "请用自己的话重写导读，日报只放一句话导读与链接。",
                    file=sys.stderr)
                raise SystemExit(4)
        result.append({"entry": entry, "row": by_pmid[pmid]})

    missing = sorted(set(by_pmid) - seen_pmids)
    if missing:
        print(f"[error] 以下候选缺导读，请补全后再渲染：{', '.join(missing)}", file=sys.stderr)
        raise SystemExit(3)
    return result


def fmt_authors(row: dict) -> str:
    authors = row.get("authors") or []
    if not authors:
        return "作者未列出"
    if len(authors) <= AUTHOR_LIMIT:
        return ", ".join(authors)
    return ", ".join(authors[:AUTHOR_LIMIT]) + " 等"


def fmt_meta(row: dict) -> str:
    journal = row.get("journal_iso") or row.get("journal") or "期刊未知"
    parts = [journal]
    if row.get("pubdate"):
        parts.append(row["pubdate"])
    doi = row.get("doi")
    if doi:
        parts.append(f"DOI: {doi}")
    else:
        parts.append("无 DOI")
    return " · ".join(parts)


def render_entry(number: int, row: dict, entry: dict, with_digest: bool) -> list[str]:
    title = row.get("title") or "(无标题)"
    url = row.get("pubmed_url") or f"https://pubmed.ncbi.nlm.nih.gov/{row.get('pmid')}/"
    lines = []
    if with_digest:
        lines.append(f"### {number}. [{title}]({url})")
        lines.append(f"`{fmt_meta(row)}` · {fmt_authors(row)}")
        one_liner = str(entry.get("one_liner") or "").strip()
        lines.append(f"- **导读**：{one_liner}")
        reason = str(entry.get("reason") or "").strip()
        if reason:
            lines.append(f"- **理由**：{reason}")
    else:
        keywords = "、".join(row.get("matched_keywords") or [])
        lines.append(f"- {number}. [{title}]({url}) — {fmt_meta(row)} · 命中：{keywords}")
    return lines


def render(candidates: dict, entries: list[dict]) -> str:
    run_date = candidates.get("run_date") or ""
    stats = candidates.get("stats") or {}
    interests = str(candidates.get("research_interests") or "").strip()
    keywords = candidates.get("keywords") or []
    reldate = (candidates.get("window") or {}).get("reldate", "?")

    lines = [f"# 医学文献日报 · {run_date}", ""]
    counts = {b: sum(1 for e in entries if e["entry"]["bucket"] == b) for b in BUCKETS}
    lines.append(f"> 候选 {len(entries)} 篇（已去重）｜🔴 必读 {counts['must_read']}"
                 f" ｜🟡 值得扫一眼 {counts['worth_a_look']}"
                 f" ｜⚪ 可跳过 {counts['skip']}")
    if interests:
        lines.append(f"> 研究方向：{interests}")
    lines.append("")

    number = 0
    for bucket in BUCKETS:
        heading, with_digest = BUCKET_META[bucket]
        bucket_entries = [e for e in entries if e["entry"]["bucket"] == bucket]
        lines.append(f"## {heading}")
        lines.append("")
        if not bucket_entries:
            lines.append("（本档今日为空）")
            lines.append("")
            continue
        for item in bucket_entries:
            number += 1
            lines.extend(render_entry(number, item["row"], item["entry"], with_digest))
            lines.append("")

    lines.append("## 统计")
    lines.append("")
    lines.append(f"| 关键词 | 近 {reldate} 天命中 | 取回 |")
    lines.append("| --- | --- | --- |")
    for kw in keywords:
        lines.append(f"| {kw.get('keyword', '')} | {kw.get('count', 0)} | {kw.get('returned', 0)} |")
    lines.append("")
    lines.append(f"- 窗口内命中共 {stats.get('esearch_hits', 0)} 篇；本轮去重前 "
                 f"{stats.get('union', 0)} 篇，已看过跳过 {stats.get('already_seen', 0)} 篇，"
                 f"实际收录 {stats.get('new', len(entries))} 篇。")
    lines.append("- 版权说明：本日报只含一句话导读、链接与元数据，不含摘要原文；"
                 "全文请点击链接到 PubMed/出版方阅读。导读为 AI 生成，仅供筛读参考，"
                 "结论以原文为准。")
    lines.append("")
    return "\n".join(lines)


def main(args: list[str]) -> int:
    """args 不含程序名：args[0]=候选清单，args[1]=导读 JSON（与单测调用一致）。"""
    args = [a for a in args if a not in {"-h", "--help"}]
    if len(args) < 2:
        print(__doc__.strip())
        return 0
    candidates_path, verdicts_path = Path(args[0]), Path(args[1])
    output = args[args.index("-o") + 1] if "-o" in args else None

    candidates = load_json(candidates_path)
    verdicts = load_json(verdicts_path)
    try:
        entries = validate(candidates, verdicts)
    except SystemExit as exc:  # 校验失败：中文原因已打到 stderr
        return exc.code if isinstance(exc.code, int) else 3
    markdown = render(candidates, entries)

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")
        counts = {b: sum(1 for e in entries if e["entry"]["bucket"] == b) for b in BUCKETS}
        print(f"[render] 必读 {counts['must_read']} · 值得扫一眼 {counts['worth_a_look']}"
              f" · 可跳过 {counts['skip']}")
        checked = sum(1 for e in entries if (e["row"].get("abstract") or "")
                      and e["entry"]["bucket"] != "skip")
        print(f"[render] 防抄袭校验通过（对照 {checked} 篇摘要，阈值连续 {PLAGIARISM_N} 词）")
        print(f"[done] 日报 → {out_path}")
    else:
        sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
