# E-utilities 使用要点（PubMed 抓取的参数与限速备忘）

本文是 `scripts/fetch_pubmed.py` 的参数依据速查。官方文档：
[E-utilities Quick Start (NBK25500)](https://www.ncbi.nlm.nih.gov/books/NBK25500/)、
[Chapter 4 端点详解 (NBK25499)](https://www.ncbi.nlm.nih.gov/books/NBK25499/)、
[频率限制与 api_key (NBK25497)](https://www.ncbi.nlm.nih.gov/books/NBK25497/)。
参数核对日期 2026-09-19，2026-11-02 复核并按实测修订（v0.2.0）。

## esearch.fcgi（检索出 PMID 列表）

| 参数 | 本仓库取值 | 说明 |
| --- | --- | --- |
| `db` | `pubmed` | 必选 |
| `term` | 用户关键词 | 需 URL 编码；也支持完整检索式（如 `sepsis[Title/Abstract] AND adaptive[Title]`） |
| `datetype` | `edat` | Entrez 入库日期，最适合增量（`pdat` 是出版日期，对 ahead-of-print 会漏检） |
| `reldate` | 默认 7 | 最近 n 天；与 `mindate/maxdate` 二选一（后者必须成对，格式 YYYY/MM/DD） |
| `retmax` | `id_limit`（默认 1000） | esearch 只取 ID，开销小；取足后在本地先与 seen 去重，再按 config 的 `retmax`（每词每轮最多新收录篇数）截取。v0.1.x 直接用 retmax 截断 esearch，已读文献会占满名额（"seen 饿死"） |
| `sort` | **不传** | 不传即 PubMed 默认 Most Recent（按入库时间新→旧，PubMed Help："the date a record was initially added to PubMed, not the publication date"），与 edat 窗口同口径。2026-11-02 实测：`most+recent`/`recently added` 会被报 "Unknown sort schema … ignored"；`pub_date` 按出版日期排，会把提前定档的 ahead-of-print（如 "2026 Dec"）排到最前、挤掉真正新入库的条目（v0.1.x 的做法） |
| `retmode` | `json` | 解析 `count`、`idlist`，以及 `querytranslation`、`errorlist`、`warninglist`（拼错的词会被静默忽略、HTTP 仍是 200，必须读这两个列表才能发现） |

## efetch.fcgi（批量取元数据与摘要）

- 参数：`db=pubmed&id=<逗号分隔 PMID>&rettype=abstract&retmode=xml`
  （`retmode=text` 的人读格式不适合机器解析）。
- efetch / esummary **不接受** `term/sort/datetype/reldate`，那些是 esearch 参数。
- 返回 `PubmedArticleSet`：期刊文章是 `<PubmedArticle>`（`<Article>` 位于
  `<MedlineCitation>` 之下）；**图书章节（StatPearls 等）是 `<PubmedBookArticle>`，
  结构完全不同**——esearch on db=pubmed 会命中它们，必须同时处理（真实运行踩过的坑）。
- DOI 取 `PubmedData/ArticleIdList/ArticleId[@IdType="doi"]`；只有 pii/elocationid
  的条目没有 DOI。摘要可能缺失，或带 `Label` 属性的结构化多段（拼接时保留段标签）。
- 每批 ≤200 个 PMID；本仓库按 100 分批。

## esummary.fcgi（本仓库未用的轻量替代）

`retmode=json` 时返回 title/journal/pubdate/authors/doi 等元数据，**但无摘要**。
日报需要摘要给 Agent 做相关性判断，故主路径用 efetch；想省流量可先用 esummary
粗筛再对幸存者 efetch。

## 频率限制（硬规则）

- 无 `api_key`：**3 req/s**（所有 E-utilities 端点合计），超速可能被封 IP；
  有 api_key（NCBI 账户设置里创建，用法 `&api_key=...`）：10 req/s。
- 超限返回 HTTP 429（体如 `{"error":"API rate limit exceeded","count":"11"}`，
  [NLM KA-05510](https://support.nlm.nih.gov/kbArticle/?pn=KA-05510)）。本仓库对 429/5xx/
  网络瞬断最多重试 2 次（等待 2s、5s，若有 Retry-After 取较大者，上限 60s）。
- 本仓库默认请求间隔 **1.1s**（实际约 0.9 req/s，对共享服务温柔），`--sleep` 可调
  但下限 0.4s。所有请求带 `tool` 与 `email` 参数，便于 NCBI 联系。
- E-utilities 对 GitHub Actions 等共享出口 IP 不友好——本仓库定位本地优先，
  定时任务请用本机 cron（见 docs/usage.md），不要上 CI。

## 增量去重策略（v0.2.0）

- 每日 esearch（edat 窗口）取全量 ID → 与 `data/seen.json` 求差 → 每关键词按 Most Recent
  顺序收录至多 `retmax` 篇 → 只对收录的调 efetch。超出部分**顺延**：不写 seen，下次
  运行仍在窗口内就会出现；日报统计区明示顺延篇数。
- **自上次以来**：seen 文件的 `updated` 是上次标记已读的日期；距今超过 reldate 天时窗口
  自动扩到 gap+1 天（多 1 天重叠由 seen 兜底，上限 60 天，`auto_catchup: false` 可关）。
  对齐 My NCBI What's New "记住上次取新时间"的语义。
- **两阶段提交（推荐）**：`fetch_pubmed.py --no-commit` 只读 seen；Agent 分档、
  `render_digest.py --commit-seen data/seen.json` 日报落盘成功后才把本期 PMID 写入 seen。
  不加 `--no-commit` 时保持 v0.1.x 行为（抓取即写 seen）。
- seen 写回是原子的（tmp + `os.replace`），中断不会留下半截状态文件。
- edat 对"出版超 12 个月才入库"的引文取出版日期（PubMed Help），这类补录旧文不会进窗口，
  这是有意为之。

## 出版类型标记

efetch 解析时输出 `flags`：`retracted`（Retracted Publication 或 CommentsCorrections
RetractionIn）、`concern`（ExpressionOfConcernIn）、`notice`（Retraction Notice / 旧名
Retraction of Publication / Published Erratum / Expression of Concern）、`preprint`、
`opinion`（Comment/Editorial/Letter/News）、`book`。2026-11-02 实测旧名
`"retraction of publication"[pt]` 已检索不到，当前名为 `Retraction Notice`。
