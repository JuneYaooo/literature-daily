# 使用与维护文档

## 每日流程

```bash
# 1. 增量抓取（3 关键词默认 4 次请求，约 5 秒）
python3 scripts/fetch_pubmed.py config.json --seen data/seen.json -o data/candidates.json

# 2. 把 data/candidates.json 交给 Agent 分档导读（见 SKILL.md），得到 verdicts.json 后渲染
python3 scripts/render_digest.py data/candidates.json data/verdicts.json -o reports/2026-09-19.md
```

## config.json 字段

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `keywords` | 必填 | PubMed 关键词/检索式列表（如 `"sepsis biomarker"`、`"abc[Title] AND xyz"`） |
| `retmax` | 15 | 每个关键词单次最多取回多少篇（截断风险见命中数日志） |
| `reldate` | 7 | 增量窗口：最近 n 天（按 Entrez 入库日期 edat） |
| `research_interests` | 空 | 你的研究方向描述，Agent 分档的唯一依据，写具体可显著提升分档质量 |
| `email` | 空 | 建议填写，NCBI 超速时用于联系你 |
| `tool` | `literature-daily` | NCBI 请求的 tool 标识 |

## fetch_pubmed.py 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `config`（位置参数） | 必填 | 配置 JSON 路径 |
| `--seen PATH` | 不去重 | seen 状态文件路径；原子写回（tmp + rename） |
| `-o, --output PATH` | stdout | 候选清单 JSON 输出路径 |
| `--offline DIR` | 联网 | 离线模式：从 DIR 读 `esearch_kw{n}.json` 与 `efetch_v1.xml` 夹具 |
| `--date YYYY-MM-DD` | 今天 | 记录到产物中的运行日期；评测复现时固定 |
| `--api-key KEY` | 环境 `PUBMED_API_KEY` | NCBI api_key（10 req/s）；只从命令行/环境变量读取，勿写入仓库 |
| `--sleep SECONDS` | 1.1 | 请求间隔；下限强制 0.4s（NCBI 无 key 3 req/s） |
| `--strip-abstract` | 关闭 | 输出候选清单时抹掉摘要字段（发布评测产物用） |

## render_digest.py 参数与导读格式

`python3 scripts/render_digest.py candidates.json verdicts.json -o report.md`

verdicts.json 每篇候选一条：`{"pmid": "...", "bucket": "must_read|worth_a_look|skip",
"one_liner": "中文一句话", "reason": "..."}`。must_read 必须有 one_liner 与 reason；
skip 可只给 pmid + bucket。渲染前强制校验：one_liner/reason 中出现摘要原文连续
≥25 词片段即退出码 4，不落盘日报。

## 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 2 | 输入文件不存在（fetch 与 render 相同） |
| 3 | 输入格式/覆盖错误（非法 JSON、缺 keywords、坏 seen、导读缺漏或含未知 PMID，stderr 给中文原因） |
| 4 | 仅 render：导读照抄摘要 ≥25 词，拒绝渲染 |

## 定时运行（本机 cron，仅文档示例，本仓库不含任何定时配置）

```bash
# crontab -e：每个工作日 07:30 抓取；Agent 分档建议手动触发以确认分档质量
30 7 * * 1-5 cd /path/to/literature-daily && python3 scripts/fetch_pubmed.py config.json --seen data/seen.json -o data/candidates.json >> data/fetch.log 2>&1
```

## 测试与评测复现

```bash
python3 -m unittest discover tests                                        # 27 项，全程离线
python3 scripts/fetch_pubmed.py evals/fixtures/config_offline_v1.json \
    -o /tmp/candidates.json --offline evals/fixtures/offline_v1 --date 2026-09-19
python3 scripts/render_digest.py /tmp/candidates.json \
    evals/fixtures/verdicts_good_v1.json -o /tmp/digest.md
```

离线运行同输入两次 sha256 一致（候选 `3d2c80e1…`、日报 `c1a727e0…`）。
完整评测流程见 [evals/README.md](../evals/README.md)。

## 发布评测产物时的版权注意

真实运行抓到的摘要是出版方版权内容，入库共享前请用 `--strip-abstract` 重跑或对产物
本地脱敏（本仓库 runs_v1 里的 live 候选清单已脱敏），只保留元数据与改写导读。
