# 迭代记录：从失败到修复

## 迭代 1（v0.1.0 开发期）：CLI 参数接口与解析路径双缺陷（单测抓到）

- 过程：首轮 26 项单测中 13 项失败。两个根因：
  1. `main()` 假定参数列表首元素是程序名（照搬 `sys.argv` 习惯），单测把配置路径
     作为首元素传入时被丢弃，脚本把第二个参数当配置，直接打印帮助返回 0；
  2. XML 解析把 `<Article>` 当作 `<PubmedArticle>` 的直接子节点，而真实 PubMed XML
     里它在 `<MedlineCitation>` 之下，导致 title/abstract/作者全部解析为空——
     防抄袭门因此形同虚设（对照 0 篇摘要）。
- 修复：`main()` 改为直接吃参数列表（`__main__` 里传 `sys.argv[1:]`）；全部解析路径
  加 `MedlineCitation/` 前缀；标题等混合标记字段改用 `itertext()` 提取
  （`findtext` 会在子元素处截断，"Serum <i>procalcitonin</i>…" 只剩 "Serum"）。
- 另修：ElementTree 的无子元素节点布尔值为 False，不能用 `or` 链找节点，必须判 `None`。

## 迭代 2（v0.1.0，真实运行发现）：PubMed 图书章节导致抓取中断

- 过程：2026-09-19 首次真实调用（3 关键词、17 篇候选）时脚本 exit 3：
  “efetch 结果缺少 PMID：37603649”。单查该 PMID 发现 esearch on db=pubmed 会命中
  StatPearls 等**图书章节**，efetch 以 `<PubmedBookArticle>`（结构完全不同）返回，
  解析器只认 `<PubmedArticle>`。
- 修复：新增 `parse_book_article`，把图书条目映射为统一字段结构并标
  `pubtypes=["Book"]`，交由 Agent 分档（合成样例中归入可跳过）；夹具补入合成图书
  条目 99010006 作回归，`test_book_article` 覆盖。
- 教训：esearch 的"命中"≠"期刊论文"，日报管线必须容忍 PubMed 全库的对象类型。

| 指标 | 修复前 | 修复后 |
| --- | --- | --- |
| 真实 17 篇抓取 | exit 3 中断 | 全部解析成功 |
| 单元测试 | 13 项失败 | 27/27 通过 |

## 迭代 3（v0.1.0，评测夹具审查时发现）：限速口径与铁律冲突

- 过程：任务规范写"限速 sleep 0.4s"，同时铁律要求"对 NCBI 温柔（实际 ≤1 req/s）"——
  0.4s 间隔理论上可到 2.5 req/s，逼近无 key 上限 3 req/s。
- 处置：默认间隔定为 1.1s（实测约 0.9 req/s），`--sleep` 可调但强制下限 0.4s
  （NCBI 无 key 3 req/s 的硬底线），低于下限打印警告并钳制。两个约束同时满足。

## 回归 4（2026-09-19 第二次联网回归，v0.1.1）：seen 跨运行去重与 edat 时间窗复核

- 过程：沿用首次真实运行写下的 `data/seen.json`（17 篇），用 config.example.json 再跑一次
  真实抓取（3 次 esearch、间隔 1.1s）：命中仍为 33/12/14，**17 篇全部命中 seen、新增 0、
  未调 efetch**，seen 文件内容不变——"上次见过的不再出现"在真实数据上二次成立。
- edat 时间窗：同一关键词 reldate=1/7/30 各跑一次小 retmax，命中数 11→33→147 单调递增，
  窗口参数真实生效；reldate=1 的 top-3 恰为首次运行 kw1 候选前三且全部在 seen 中。
- 新观察（非缺陷，已写入 eutils-notes）：reldate=30 且 `sort=pub_date` 时前三名是提前定档的
  ahead-of-print（pubdate 2026 Dec/Nov 15/Oct 15，均不在 7 天窗口）——扩窗会把"刊期更靠后"
  的条目排到最前；edat 窗口语义本身不受影响，7 天默认窗口下无此现象。
- 日增口径复核：`journal article[pt]` 近 1 天命中 8,595（同日晚间）≥ README 记载的
  7,773（同日早间），声明自洽。
- 顺带加固两处（行为不变于既有产物，全部 sha256 复核一致）：
  1. 渲染分组排序改为**同 bucket 内按候选清单顺序**（esearch pub_date 新→旧），不再随
     verdicts 文件条目顺序的偶然差异而变；新增测试 `test_bucket_order_follows_candidates_not_verdict_order`。
  2. seen 写回时收敛重复 PMID（`sorted(set(...))`），手工编辑留下的重复项不会累积；
     新增测试 `test_seen_duplicates_collapsed`；并消掉关键词匹配循环里的重复 `set()` 构造。
- 证据：[live_transcript_v2.txt](runs_v1/live_transcript_v2.txt)（逐字）、
  [live_regression2_2026-09-19.json](runs_v1/live_regression2_2026-09-19.json)（结构化结论，
  共 11 次请求）；哈希见 [hashes_v2.json](runs_v1/hashes_v2.json)。

## 迭代 5（v0.2.0，2026-11-02）：对标调研驱动的逻辑审查

调研见 [references/benchmarks.md](../references/benchmarks.md)。先用 v0.1.1 原样跑真实
PubMed 留下基线（[runs_v2/before/](runs_v2/before/)），改完用同一配置重跑
（[runs_v2/after/](runs_v2/after/)），对比汇总在 [runs_v2/comparison_v2.json](runs_v2/comparison_v2.json)。

### 问题清单（按影响排序）

| # | 问题 | 依据 | 影响 | 处置 |
| --- | --- | --- | --- | --- |
| 1 | **seen 饿死**：retmax 截断发生在去重之前；窗口内前 retmax 名一旦已读，其余新文献永远不出现 | 实测：命中 94、去重后 87；改前首跑 17 篇，同日复跑 0 新增 | 静默漏掉大部分文献，且 v0.1.1 回归（迭代记录"回归 4"与 case c6）把这个 0 当成了"去重生效"的证据 | **改**：先取足 ID（id_limit）→ 去重 → 每词截取 retmax；超出部分顺延、不写 seen、日报明示 |
| 2 | **排序口径错**：`sort=pub_date` 按出版日期，与 edat 窗口不一致，ahead-of-print（"2026 Dec"）排第一，真正新入库的被挤出 | PubMed Help：Most Recent 按入库日期；实测 pub_date 排序把 10-31 入库条目排到 10-26 之后 | 截断时优先丢掉最新入库的文献 | **改**：不传 sort（默认 Most Recent）；首跑候选近 2 天入库占比 41%→72% |
| 3 | **检索式被静默放宽/反转** | 实测 `biomarkr` 被丢弃（命中 312）；`AND NOT` 的 NOT 被丢弃导致只检索预印本（命中 0） | 用户以为在订阅 A，实际收到 B | **改**：记录 querytranslation、errorlist、warninglist，终端 `[warn]` + 日报 ⚠️ |
| 4 | **抓取即写 seen**：定时抓取后没分档，下一次抓取覆盖候选清单，文献永久丢失 | 旧 usage 推荐 cron 抓取 + 人工分档；My NCBI 只在发送后推进"上次" | 漏文献 | **改**：`--no-commit` + `render --commit-seen` 两阶段提交（默认行为不变，SKILL 默认流程改用两阶段） |
| 5 | 固定 reldate，停跑 >7 天就漏 | My NCBI What's New 记住上次取新时间 | 假期后漏文献 | **改**：按 seen.updated 自动补窗（gap+1 天，上限 60，可关） |
| 6 | 撤稿/勘误/关注声明/预印本无标识 | 实测近 30 天勘误 2,121、预印本 1,810、撤稿声明 281；旧名 "Retraction of Publication" 已检索不到 | 把撤稿文章推成必读是研究诚信事故 | **改**：`flags` + 日报徽标 + 渲染器拒绝把已撤稿文献列为必读（退出码 3）+ SKILL 规则（预印本须注明） |
| 7 | 网络瞬断/429 直接失败 | 改前基线真实遇到 SSL EOF；NLM 429 说明 | 定时任务偶发失败 | **改**：最多重试 2 次（2s/5s，尊重 Retry-After） |
| 8 | esearch 返回 `ERROR` 字段时报"解析失败 KeyError" | 代码审查 | 报错难懂 | **改**：直接给出 PubMed 的错误原文（退出码 3） |
| 9 | 分档只看 research_interests，LLM 初筛召回不稳定 | JMIR 2025 汇总敏感度 0.73（修订提示后 0.98，CI 宽） | 漏必读 | **改（指令层）**：SKILL 规定拿不准就高不就低；skip 只用于仅字面命中 |
| 10 | 裸关键词命中无关领域 | 实测 "early warning score" 命中水电站轴承、牛呼吸道病；加 `[tiab] AND sepsis` 后 18→7 | 噪声 | **改（文档）**：SKILL/usage 给出字段标签与 Clinical Queries 写法，均实测可用 |
| 11 | 无用户反馈闭环（Semantic Scholar/LitSuggest/Scholar Inbox 都有） | 对标调研 | 分档不会越用越准 | **不改**：需要设计反馈存储与使用方式，留作下一版 |
| 12 | 无影响因子/分区过滤 | Stork、medpapers-daily | — | **不改**：商业授权数据；研究设计比影响因子更能反映单篇质量 |
| 13 | 防抄袭阈值 25 词无文献依据 | 未找到针对一句话导读的标准 | 中文整句翻译挡不住 | **不改阈值**：在 SKILL 里明确禁止整句翻译，阈值仅防直接粘贴 |
| 14 | 顺延条目按入库新→旧取，若每天新增都超过 retmax，最老的会滑出窗口 | 设计推演 | 宽检索式下仍会漏，但现在有明示 | **不改**：日报每期写出顺延数并建议收窄；不做无限积压队列 |

### 改前/改后（同一配置、同日真实运行）

| 指标 | v0.1.1 | v0.2.0 |
| --- | --- | --- |
| 首跑后可见的未读新文献 | 17（其余 70 篇无提示） | 收录 18 + 明示顺延 69 |
| 同日复跑新增 | **0** | 18（再跑仍有顺延 51） |
| 首跑候选近 2 天入库占比 | 7/17 | 13/18 |
| 拼错关键词 | 无提示 | `[warn]` + 日报 ⚠️ 与实际检索式 |
| `--no-commit` 连跑两次 | 不支持 | seen 不变、候选一致（12 篇） |
| 撤稿/勘误/预印本标记 | 无 | 5 个真实 PMID 全部判对 |

### 兼容性与产物变化

- config 字段不变，`retmax` 语义从"esearch 截断数"改为"每词每轮最多新收录数"——对
  已有配置是放宽（不会更少），新增可选 `id_limit`、`auto_catchup`。
- 候选清单 schema 1.0→1.1：新增 `flags`、`deferred_pmids`、`keywords[].new/scanned/
  query_translation/warnings`、`window.base_reldate/last_run/sort/id_limit`，`stats.deferred`；
  渲染器兼容旧清单（有单测）。
- 离线夹具的候选与日报 sha256 因新增字段/徽标/统计列而变化，新值见 docs/usage.md；
  同输入两次运行仍一致。
- 单元测试 29→61 项。

## 已知限制（截至 v0.2.0）

- 相关性分档与中文导读是 AI 生成（model_only 自评），未经医学信息学背景的人工复核；
  导读仅供筛读，结论必须回到原文。
- 增量窗口用 `datetype=edat`：出版超 12 个月才入库的补录旧文不会进窗口（PubMed 规则，
  有意为之）。~~固定 reldate 不回溯~~ v0.2.0 已按上次运行日期自动补窗。
- ~~retmax 静默截断~~ v0.2.0 改为先去重再截取、超出顺延并明示；但检索式持续过宽时，
  顺延条目仍可能滑出窗口（日报会提示）。命中超过 id_limit（默认 1000）时只与最近入库
  的部分去重，会告警。
- 无用户反馈闭环：分档不会根据"这篇其实不相关"的反馈越用越准。
- 一次只处理一个 config；多账号/多方向订阅需分别运行。
