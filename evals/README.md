# 评测（Evals V1）

本目录保存 literature-daily 的行为证据：题集、量表、运行协议、真实产物与逐题判断。

## 评测分层

1. **脚本行为层**：对 `evals/fixtures/` 的合成夹具运行 `scripts/fetch_pubmed.py` 与
   `scripts/render_digest.py`（离线模式，固定 `--date 2026-09-19`），逐条核对
   [cases_v1.jsonl](cases_v1.jsonl) 的 required/forbidden 原子检查；确定性用例
   （c3 去重、c5 渲染）显式双跑验证 sha256。单元测试 27 项：`python3 -m unittest discover tests`。
2. **Agent 工作流层**：Agent 读取 **2026-09-19 真实调用 PubMed 得到的 17 篇候选**
   （[runs_v1/live_candidates_v1.json](runs_v1/live_candidates_v1.json)，摘要字段已脱敏），
   对照研究兴趣分档并撰写中文一句话导读（[runs_v1/live_verdicts_v1.json](runs_v1/live_verdicts_v1.json)），
   渲染为 [runs_v1/live_digest_2026-09-19.md](runs_v1/live_digest_2026-09-19.md)，
   按 [rubric_v1.md](rubric_v1.md) 三维度判定（case c8）。

## 当前状态（2026-09-19，v0.1.0）

- **8/8 用例通过，0 硬失败**；逐题判断见 [judgments_v1.jsonl](judgments_v1.jsonl)，
  汇总见 [summary_v1.json](summary_v1.json)。
- 三轮真实失败与修复见 [iteration_notes.md](iteration_notes.md)：单测抓到 CLI 参数接口
  与 XML 解析路径双缺陷；**真实调用抓到 PubMed 图书章节（StatPearls 类）解析中断**并已
  回归；限速口径按"默认 1.1s、下限 0.4s"落地。
- 夹具全部为合成样本（PMID 99010001–99010006 为占位编号，标题/作者/摘要均虚构，
  见 [fixtures/README.md](fixtures/README.md)）；真实运行的入库产物已做摘要脱敏
  （`abstract_redacted=true`），避免转载出版方版权内容。
- 已知限制：判定为开发 Agent 自评（model_only），未独立人工复核；相关性分档质量
  尤其需要目标用户抽查。离线确定性：候选清单 sha256 `3d2c80e1…`、日报
  `c1a727e0…` 两次运行一致（[runs_v1/hashes_v1.json](runs_v1/hashes_v1.json)）。

## 复现

- 单元测试（离线）：`python3 -m unittest discover tests`
- 离线全流程：见 [docs/usage.md](../docs/usage.md) 的评测复现一节
- 真实运行：需要能访问 eutils.ncbi.nlm.nih.gov 的网络；温和调用（默认间隔 1.1s）
