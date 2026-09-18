---
name: literature-daily
description: 把用户自己的 PubMed 关键词订阅变成每日文献日报：脚本增量抓取并本地去重，Agent 对照研究方向做相关性分档（必读/值得扫一眼/可跳过）并给每篇一句中文导读，渲染成 markdown 日报；只含导读、链接与元数据，绝不复制摘要原文，用于每天几分钟扫完本领域新文献。
---

# 医学文献日报（literature-daily）

当用户要"帮我追踪 PubMed 新文献""出一份文献日报""这个方向最近有什么新论文"时使用本
Skill。交付物是一份**分好档、带中文一句话导读的 markdown 日报**，不是文献数据库检索结果。

## 工作边界

- 只处理用户 config 里的关键词与研究方向；抓取走 NCBI E-utilities，默认请求间隔 1.1s
  （实际约 0.9 req/s），不要调低到 0.4s 以下，不要并发请求。`--api-key` 只从命令行或
  环境变量读，绝不写入仓库或产物。
- **版权红线**：日报只放一句话导读、链接与元数据。导读必须是自己的话；渲染脚本会拒绝
  含摘要原文连续 ≥25 词片段的导读（退出码 4）。不要试图绕过它，也不要把摘要粘进日报。
- 导读是 AI 生成的筛读参考，必须提醒用户：结论以原文为准，必读篇目要点开读。
- 关键词命中的"图书章节"（StatPearls 类，pubtypes 含 Book）默认可跳过，除非用户明确
  要教学材料。

## 默认流程

1. **准备配置**：确认用户的 [config.json](config.example.json)——`keywords` 列表、
   `research_interests`（研究方向描述，分档质量的唯一依据，没有就先问用户）、
   `retmax`（默认 15）、`reldate`（默认 7 天）。首次使用给用户看一份配置确认。
2. **增量抓取**：`python3 scripts/fetch_pubmed.py config.json --seen data/seen.json
   -o data/candidates.json`。脚本负责 esearch → 去重 → efetch，参数依据见
   [references/eutils-notes.md](references/eutils-notes.md)。网络不通时可用
   `--offline evals/fixtures/offline_v1` 演示流程（产物标 offline=true，不得冒充真实数据）。
3. **分档导读**：读候选清单的标题与摘要，对照 `research_interests` 给每篇标
   `bucket`（must_read / worth_a_look / skip）并写中文一句话导读（一句、含方法学要点、
   自己的话）。must_read 须附推荐理由；skip 不写导读。产出 verdicts JSON。
4. **渲染日报**：`python3 scripts/render_digest.py data/candidates.json verdicts.json
   -o reports/<日期>.md`。校验被拒（退出码 4）时改写导读后重跑，不要手工绕过。
5. **交代边界**：交付时说明分档依据、哪些关键词被截断（命中数 ≫ 取回数）、
   AI 导读需读原文确认；参数与退出码见 [docs/usage.md](docs/usage.md)。

## 支持文件

- [references/eutils-notes.md](references/eutils-notes.md)：E-utilities 参数、限速与
  增量去重备忘（排障时读）。
- [references/benchmarks.md](references/benchmarks.md)：与 Stork/My NCBI/Elicit 等的
  定位对比（被问"和 Stork 有什么区别"时读）。
- [docs/usage.md](docs/usage.md)：命令行参数、退出码、定时运行与评测复现。
- [evals/README.md](evals/README.md)：评测证据入口。
