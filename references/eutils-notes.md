# E-utilities 使用要点（PubMed 抓取的参数与限速备忘）

本文是 `scripts/fetch_pubmed.py` 的参数依据速查。官方文档：
[E-utilities Quick Start (NBK25500)](https://www.ncbi.nlm.nih.gov/books/NBK25500/)、
[Chapter 4 端点详解 (NBK25499)](https://www.ncbi.nlm.nih.gov/books/NBK25499/)、
[频率限制与 api_key (NBK25497)](https://www.ncbi.nlm.nih.gov/books/NBK25497/)。
参数核对日期 2026-09-19。

## esearch.fcgi（检索出 PMID 列表）

| 参数 | 本仓库取值 | 说明 |
| --- | --- | --- |
| `db` | `pubmed` | 必选 |
| `term` | 用户关键词 | 需 URL 编码；也支持完整检索式（如 `sepsis[Title/Abstract] AND adaptive[Title]`） |
| `datetype` | `edat` | Entrez 入库日期，最适合增量（`pdat` 是出版日期，对 ahead-of-print 会漏检） |
| `reldate` | 默认 7 | 最近 n 天；与 `mindate/maxdate` 二选一（后者必须成对，格式 YYYY/MM/DD） |
| `retmax` | 默认 15 | 单次取回上限，最大 10,000；命中数在 `count` 字段，可发现截断 |
| `sort` | `pub_date` | 按日期新→旧；默认 Best Match 不适合日报 |
| `retmode` | `json` | 解析 `esearchresult.count` 与 `esearchresult.idlist` |

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
- 本仓库默认请求间隔 **1.1s**（实际约 0.9 req/s，对共享服务温柔），`--sleep` 可调
  但下限 0.4s。所有请求带 `tool` 与 `email` 参数，便于 NCBI 联系。
- E-utilities 对 GitHub Actions 等共享出口 IP 不友好——本仓库定位本地优先，
  定时任务请用本机 cron（见 docs/usage.md），不要上 CI。

## 增量去重策略

- `data/seen.json` 记录已处理 PMID；每日 esearch 结果与 seen 求差，只对新 PMID 调 efetch。
- seen 写回是原子的（tmp + `os.replace`），中断不会留下半截状态文件。
- `edat` 会随 in-process 记录更新而"重见"部分条目——seen 集合天然兜底；连续多日
  没跑的用户建议临时调大 reldate 补窗口。
