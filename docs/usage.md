# 使用与维护文档

## 每日流程

```bash
# 1. 增量抓取，只读 seen（3 关键词通常 4 次请求，约 5 秒）
python3 scripts/fetch_pubmed.py config.json --seen data/seen.json --no-commit -o data/candidates.json

# 2. 把 data/candidates.json 交给 Agent 分档导读（见 SKILL.md），得到 verdicts.json 后渲染，
#    日报成功落盘后才把本期 PMID 标记为已读
python3 scripts/render_digest.py data/candidates.json data/verdicts.json \
    -o reports/2026-11-02.md --commit-seen data/seen.json
```

## config.json 字段

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `keywords` | 必填 | PubMed 关键词/检索式列表（如 `"sepsis biomarker"`、`"abc[Title] AND xyz"`） |
| `retmax` | 15 | **每个关键词每轮最多收录的新文献篇数**（v0.2.0 起在去重之后截取；超出部分顺延到下次，不标已读） |
| `reldate` | 7 | 增量窗口下限：最近 n 天（按 Entrez 入库日期 edat）；距上次运行更久会自动补窗 |
| `id_limit` | 1000 | esearch 每个关键词最多扫描的 ID 数（≤10000）；命中超过它会告警 |
| `auto_catchup` | true | 距上次运行（seen 的 `updated`）超过 reldate 天时，窗口自动扩到 gap+1 天（上限 60） |
| `research_interests` | 空 | 你的研究方向描述，Agent 分档的唯一依据，写具体可显著提升分档质量 |
| `email` | 空 | 建议填写，NCBI 超速时用于联系你 |
| `tool` | `literature-daily` | NCBI 请求的 tool 标识 |

## fetch_pubmed.py 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `config`（位置参数） | 必填 | 配置 JSON 路径 |
| `--seen PATH` | 不去重 | seen 状态文件路径；原子写回（tmp + rename），只写本轮收录的 PMID（顺延的不写） |
| `--no-commit` | 关闭 | 只读 seen 不写回；配合 render 的 `--commit-seen` 做两阶段提交（推荐） |
| `-o, --output PATH` | stdout | 候选清单 JSON 输出路径 |
| `--offline DIR` | 联网 | 离线模式：从 DIR 读 `esearch_kw{n}.json` 与 `efetch_v1.xml` 夹具 |
| `--date YYYY-MM-DD` | 今天 | 记录到产物中的运行日期；评测复现时固定 |
| `--api-key KEY` | 环境 `PUBMED_API_KEY` | NCBI api_key（10 req/s）；只从命令行/环境变量读取，勿写入仓库 |
| `--sleep SECONDS` | 1.1 | 请求间隔；下限强制 0.4s（NCBI 无 key 3 req/s） |
| `--strip-abstract` | 关闭 | 输出候选清单时抹掉摘要字段（发布评测产物用） |

## render_digest.py 参数与导读格式

`python3 scripts/render_digest.py candidates.json verdicts.json -o report.md [--commit-seen data/seen.json]`

`--commit-seen PATH`：日报校验通过并写出后，把本期全部 PMID（含 skip）原子并入 seen，
`updated` 记为候选清单的 run_date。校验失败（退出码 3/4）时不写 seen。

verdicts.json 每篇候选一条：`{"pmid": "...", "bucket": "must_read|worth_a_look|skip",
"one_liner": "中文一句话", "reason": "..."}`。must_read 必须有 one_liner 与 reason；
skip 可只给 pmid + bucket。渲染前强制校验：one_liner/reason 中出现摘要原文连续
≥25 词片段即退出码 4，不落盘日报。

## 候选清单里的新字段（schema 1.1）

| 字段 | 说明 |
| --- | --- |
| `candidates[].flags` | `retracted` / `concern` / `notice` / `preprint` / `opinion` / `book`，日报显示为徽标 |
| `keywords[].new` / `returned` | 窗口内未读篇数 / 本期日报中命中该词的篇数 |
| `keywords[].query_translation` / `warnings` | PubMed 实际执行的检索式与告警（拼错的词、未找到的引号短语） |
| `stats.deferred` / `deferred_pmids` | 超出 retmax 顺延到下次的未读篇数与 PMID |
| `window.reldate` / `base_reldate` / `last_run` | 实际窗口天数、配置值、上次标记已读的日期 |

v0.1.x 的候选清单（无这些字段）仍可被渲染。

## 检索式写法建议

- 裸词会被 PubMed 自动术语映射扩展到全字段，可能命中无关领域；用字段标签收窄，如
  `"early warning score"[tiab] AND (sepsis OR deterioration)`。
- 只要临床研究某一类设计时，可叠加 PubMed Clinical Queries 过滤器，如
  `sepsis biomarker AND (Diagnosis/Narrow[filter])`（Narrow 偏特异、Broad 偏敏感，
  依据见 references/benchmarks.md）。
- 想排除预印本：`sepsis NOT preprint[pt]`（注意不是 `AND NOT`：2026-11-02 实测 `AND NOT` 会被 PubMed 丢掉 NOT、反而只检索预印本，脚本会以 `[warn] 布尔运算符 NOT 被 PubMed 忽略` 报出）。
- 抓取日志出现 `[warn]` 时先修检索式；日报统计区的 ⚠️ 行会显示 PubMed 实际执行的检索式。

## 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 2 | 输入文件不存在（fetch 与 render 相同） |
| 3 | 输入格式/覆盖错误（非法 JSON、缺 keywords、坏 seen、导读缺漏或含未知 PMID、已撤稿文献被列为必读，stderr 给中文原因） |
| 4 | fetch：网络错误（已重试 2 次仍失败）；render：导读照抄摘要 ≥25 词，拒绝渲染 |

## 定时运行（本机 cron，仅文档示例，本仓库不含任何定时配置）

```bash
# crontab -e：每个工作日 07:30 抓取（--no-commit：没来得及分档也不会丢文献，
# 下次抓取会重新给出所有未标记已读的条目）；Agent 分档建议手动触发以确认分档质量
30 7 * * 1-5 cd /path/to/literature-daily && python3 scripts/fetch_pubmed.py config.json --seen data/seen.json --no-commit -o data/candidates.json >> data/fetch.log 2>&1
```

## 测试与评测复现

```bash
python3 -m unittest discover tests                                        # 61 项，全程离线
python3 scripts/fetch_pubmed.py evals/fixtures/config_offline_v1.json \
    -o /tmp/candidates.json --offline evals/fixtures/offline_v1 --date 2026-09-19
python3 scripts/render_digest.py /tmp/candidates.json \
    evals/fixtures/verdicts_good_v1.json -o /tmp/digest.md
```

离线运行同输入两次 sha256 一致（v0.2.0：候选 `4e2002ef…`、日报 `0df103c9…`；
v0.1.x 为 `3d2c80e1…`/`c1a727e0…`，变化来自新增字段与徽标，见 evals/iteration_notes.md）。
完整评测流程见 [evals/README.md](../evals/README.md)。

## 发布评测产物时的版权注意

真实运行抓到的摘要是出版方版权内容，入库共享前请用 `--strip-abstract` 重跑或对产物
本地脱敏（本仓库 runs_v1 里的 live 候选清单已脱敏），只保留元数据与改写导读。
