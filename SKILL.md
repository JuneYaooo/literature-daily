---
name: literature-daily
description: 把用户自己的 PubMed 关键词订阅变成每日文献日报：脚本按入库时间增量抓取、先去重再截取（超出部分顺延不丢）、标出撤稿/勘误/预印本并提示被 PubMed 静默改写的检索式，Agent 对照研究方向做相关性分档（必读/值得扫一眼/可跳过）并给每篇一句中文导读，渲染成 markdown 日报；只含导读、链接与元数据，绝不复制摘要原文。
---

# 医学文献日报（literature-daily）

当用户要"帮我追踪 PubMed 新文献""出一份文献日报""这个方向最近有什么新论文"时使用本
Skill。交付物是一份**分好档、带中文一句话导读的 markdown 日报**，不是文献数据库检索结果。

## 工作边界

- 只处理用户 config 里的关键词与研究方向；抓取走 NCBI E-utilities，默认请求间隔 1.1s
  （约 0.9 req/s），不要调低到 0.4s 以下，不要并发请求。`--api-key` 只从命令行或
  环境变量读，绝不写入仓库或产物。
- **版权红线**：日报只放一句话导读、链接与元数据。导读必须是自己的话，也不要整句翻译
  摘要；渲染脚本会拒绝含摘要原文连续 ≥25 词片段的导读（退出码 4），不要试图绕过。
- 导读是 AI 生成的筛读参考，必须提醒用户：结论以原文为准，必读篇目要点开读。

## 默认流程

1. **准备配置**：确认用户的 [config.json](config.example.json)——`keywords`、
   `research_interests`（分档的唯一依据，没有就先问）、`retmax`（每词每轮最多收录的
   新文献，默认 15）、`reldate`（默认 7 天）。首次使用给用户看一份配置确认。
   关键词建议用 PubMed 字段标签收窄（如 `"early warning score"[tiab] AND sepsis`），
   裸词会命中无关领域（实测"early warning score"会命中水电站轴承、牛呼吸道病）。
2. **增量抓取（只读 seen）**：`python3 scripts/fetch_pubmed.py config.json --seen
   data/seen.json --no-commit -o data/candidates.json`。脚本按入库时间（Most Recent）
   取窗口内全部 ID，先与 seen 去重再截取；距上次运行超过 reldate 天会自动补窗。
   网络不通时可用 `--offline evals/fixtures/offline_v1` 演示（产物标 offline=true，
   不得冒充真实数据）。
3. **先看告警**：终端出现 `[warn]`（如"词 biomarkr 在 PubMed 中不存在，已被忽略"）说明
   检索式被 PubMed 静默放宽，**先告诉用户并建议改词**，再继续分档；出现顺延（`顺延 N 篇`）
   说明检索式过宽或 retmax 过小，在交付时说明。
4. **分档导读**：读候选清单的标题、摘要、`pubtypes` 与 `flags`，对照 `research_interests`
   给每篇标 `bucket` 并写中文一句话导读（一句、含研究设计/样本/验证方式等方法学要点）。
   - must_read 须附推荐理由；skip 不写导读，只用于"仅字面命中/与方向无关"。
   - **拿不准时就高不就低**：放 worth_a_look，不要放 skip（LLM 初筛召回不稳定，漏掉
     必读的代价高于多扫一眼）。
   - `flags` 规则：`retracted` 已撤稿——不得列为必读，若与方向相关放 worth_a_look 并在
     导读写明"已撤稿"；`notice` 撤稿声明/勘误/关注声明——默认 skip，除非它针对用户
     正在跟的文献；`preprint` 导读须注明"预印本、未经同行评审"；`book` 图书章节默认
     skip，除非用户要教学材料；`opinion` 述评/通讯按内容判断，理由里说明不是原始研究。
   产出 verdicts JSON（格式见 [docs/usage.md](docs/usage.md)）。
5. **渲染并标记已读**：`python3 scripts/render_digest.py data/candidates.json
   verdicts.json -o reports/<日期>.md --commit-seen data/seen.json`。只有日报成功落盘
   才写 seen；校验被拒（退出码 4/3）时改写导读后重跑，不要手工绕过。
6. **交代边界**：交付时说明分档依据、检索告警与顺延篇数、AI 导读需读原文确认。

## 支持文件

- [references/eutils-notes.md](references/eutils-notes.md)：E-utilities 参数、排序与日期
  口径、限速重试、增量与两阶段提交（排障时读）。
- [references/benchmarks.md](references/benchmarks.md)：与 My NCBI、Stork、Semantic Scholar、
  LitSuggest、zotero-arxiv-daily 等的逻辑对比与依据（被问"为什么这样设计/和 X 有什么
  区别"时读）。
- [docs/usage.md](docs/usage.md)：命令行参数、退出码、定时运行与评测复现。
- [evals/README.md](evals/README.md)：评测证据入口。
