# 对标与参考逻辑（2026-11-02 第二轮深度调研，扩充自 2026-09-19 首轮）

本文回答三个问题：同类产品/开源项目怎么做"文献订阅 → 降噪 → 导读"；权威资料
（PubMed/NCBI 官方文档、方法学文献）对关键口径怎么规定；本项目据此改了什么、
还差什么。每条结论都附来源与检索日期；**实测**表示本仓库在当天对 E-utilities
发出真实请求核对过，不是转述。

引用版权归原作者所有，仅作定位说明，未转载任何竞品素材。

## 1. 对标清单与对比

| 方案 | 类型 | 怎么判断"新" | 怎么降噪/排序 | 导读 | 可借鉴 | 本项目差异 |
| --- | --- | --- | --- | --- | --- | --- |
| [My NCBI 保存检索 + 邮件提醒](https://pubmed.ncbi.nlm.nih.gov/help/)（NLM，免费） | 官方 | 记住上次取新时间，只发"自上次以来"新增；What's New 不取出版超过 1 年的条目（[NCBI Help NBK53592](https://www.ncbi.nlm.nih.gov/books/NBK53592/)，经 [检索摘要](https://lib.dmu.edu/su/keepingcurrent/pubmed) 转述，原页 2026-11 有人机验证无法直读） | 无，按检索式原样推送 | 无 | **自上次以来**的窗口语义 | v0.2.0 已对齐（自动补窗）；另加语义分档与中文导读 |
| [Stork 文献鸟](https://www.storkapp.me/)（SaaS） | 商业 | 关键词订阅定期推送 | 关键词 + 期刊维度过滤（Pro "advanced filter"）；首轮调研记载 Pro 才可设影响因子阈值 | 付费 "Reading Guide" AI 摘要、邮件翻译 | 中文用户愿为"导读"付费 | 本地运行、无订阅费；不做影响因子（JCR 为商业授权数据） |
| [Semantic Scholar Research Feeds](https://www.semanticscholar.org/faq/what-are-research-feeds) | 商业免费 | 每日刷新 | 以文件夹里保存的论文为正样本，对比学习的论文向量找相似；"not relevant" 作为负反馈（[FAQ](https://www.semanticscholar.org/faq/fine-tune-research-feeds)） | 无中文 | **用户反馈闭环** | 未实现反馈闭环（见第 4 节"不改"） |
| [LitSuggest](https://pmc.ncbi.nlm.nih.gov/articles/PMC8262723/)（NCBI，Allot et al., NAR 2021） | 官方研究工具 | 可选**每周**自动扫新文献 | 用户给正/负例 PMID 训练集成模型，≥0.5 判正 | 无 | 正负例驱动、按周批处理 | 本项目用 research_interests 文本 + Agent 判断，零训练成本 |
| [Scholar Inbox](https://arxiv.org/abs/2504.08385)（Flicke et al., 2025） | 学术开源平台 | 每日 arXiv/bioRxiv | 基于用户评分训练推荐器，主动学习缓解冷启动；80 万条评分数据集 | 视觉摘要 | 评分驱动 + 冷启动处理 | 数据源不同（无 PubMed） |
| [TideDra/zotero-arxiv-daily](https://github.com/TideDra/zotero-arxiv-daily)（2026-11-02 读 README） | 开源 | 只取**前一天**发布的预印本 | Zotero 文库向量相似度加权平均，**新加入文库的条目权重更高**；最多 100 篇（`max_paper_num`） | LLM TL;DR（默认英文） | 时间衰减兴趣画像 | 无 PubMed；本项目不依赖 Zotero |
| [jeong87/paper-morning](https://github.com/jeong87/paper-morning)（2★） | 开源 | 时间范围 7 天–5 年 | 先检索后 `LLM_MAX_CANDIDATES` 截取短名单再让 LLM 打分，输出理由与证据片段 | LLM | **先粗筛再进 LLM** 控成本 | 本项目同样"先去重再截取"（v0.2.0） |
| [msberends/medpapers-daily](https://github.com/msberends/medpapers-daily)（1★） | 开源 | 每日 cron | Scopus 分区过滤 + MeSH 主题归类 + 用户相关性评分 | 无 | MeSH 主题归类 | 不引入 Scopus/Elsevier key |

GitHub 侧 PubMed 日报类开源项目在 2026-11-02 的检索中星数普遍 ≤2（`pubmed daily digest`
等 4 组查询，GitHub Search API），说明"PubMed 订阅 → 增量去重 → 语义分档 → 中文导读"
仍无成熟开源实现，这个判断与首轮一致。

## 2. 权威口径（逐条核对）

### 2.1 日期字段与排序（决定"什么算新文献"）

- **Entry Date [edat]**：PubMed 处理用日期，"Most Recent" 排序即按它"后进先出"；通常在
  引文可用后 24 小时内设定；**2008-12-15 起，出版后超过 12 个月才入库的引文，EDAT 被设为
  出版日期**（图书除外）。来源：[PubMed Help](https://pubmed.ncbi.nlm.nih.gov/help/)，2026-11-02。
  → 用 edat 做窗口天然排除"陈年旧文补录"，适合日报；代价是补录的老文献不会出现（可接受）。
- **Create Date [crdt]**：记录首次创建日期，官方说明"适合查找自上次检索以来新增的引文"。
  同上来源。
- **Most Recent 的定义**："the date a record was initially added to PubMed, not the
  publication date"，次排序为 PMID。同上来源。
- **esearch 的 sort 取值**：NCBI 文档列出 `pub_date / Author / JournalName / relevance`
  （[检索摘要转述 NBK25499](https://www.ncbi.nlm.nih.gov/books/NBK25499/)）；NLM DataGuide
  称 PubMed 默认是 most recent（[dataguide](https://dataguide.nlm.nih.gov/eutilities/utilities.html)，
  该页已停更）。**实测（2026-11-02）**：不传 sort 时 esearch 返回顺序与 PMID/入库时间
  新→旧一致；传 `most+recent`、`recently added` 均被 PubMed 以 "Unknown sort schema …
  ignored" 忽略后回落到同一默认顺序；`sort=pub_date` 则把入库于 10-31 的 42964336
  排到入库于 10-26/27 的三篇之后（因为其出版日期更早）。
  → **结论**：要"最近入库优先"，正确做法是不传 sort。

### 2.2 E-utilities 用量与错误

- 无 key 每 IP 约 3 req/s；带 api_key 默认 10 req/s，按 key 计；超限返回
  HTTP 429，示例体 `{"error":"API rate limit exceeded","count":"11"}`；长期超限会封 IP，
  解封需登记 tool/email。来源：[NLM Support KA-05510](https://support.nlm.nih.gov/kbArticle/?pn=KA-05510)、
  [NCBI Insights 2017-11-02](https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities)，
  2026-11-02 检索。官方未给出重试间隔，本项目的退避（2s、5s，尊重 Retry-After）是工程选择。
- esearch 的 retmax 单次上限：NCBI 文档 10,000；DataGuide 写 100,000（旧页）。本项目
  `id_limit` 上限按保守的 10,000。
- **实测（2026-11-02）**：esearch JSON 会返回 `querytranslation`、`errorlist`、
  `warninglist`。`sepsis biomarkr` 的 `errorlist.phrasesnotfound=["biomarkr"]`，实际
  检索式只剩 sepsis，7 天命中 312；带引号的不存在短语进入
  `warninglist.quotedphrasesnotfound`，PubMed 拆词检索。两者 HTTP 均为 200，不报错。
- **实测**：改前基线运行中遇到一次 `SSL: UNEXPECTED_EOF_WHILE_READING`，脚本直接退出。

### 2.3 出版类型（决定哪些条目不是"研究论文"）

- PubMed Help（2026-11-02）当前出版类型包含 `Retraction Notice`、`Retracted Publication`、
  `Published Erratum`、`Expression of Concern`、`Preprint`、`Corrected and Republished
  Article` 等。
- **实测**近 30 天入库：`"retraction notice"[pt]` 281 条、`"retraction of publication"[pt]`
  **0 条且 PubMed 报"短语未找到"**（旧名已不可检索，旧记录兼容保留）、
  `"published erratum"[pt]` 2,121 条、`preprint[pt]` 1,810 条、
  `"expression of concern"[pt]` 91 条。
- **实测** 5 个真实 PMID 的 efetch XML：撤稿声明带 `RetractionOf`、被撤稿文章带
  `RetractionIn` + `Retracted Publication`、勘误带 `ErratumFor`、关注声明带
  `ExpressionOfConcernFor`。结果存于 [live_flags_check.txt](../evals/runs_v2/after/live_flags_check.txt)。

### 2.4 方法学：检索过滤与 LLM 初筛

- **PubMed Clinical Queries**（Haynes 等 McMaster 过滤器）：Therapy/Diagnosis/Etiology/
  Prognosis/Clinical Prediction Guides，各有 Broad（敏感度优先，多数类别 >90%）与
  Narrow（特异度优先，12 个中 8 个 ≥94%，但敏感度可 <50%）两档
  （[Wilczynski et al., J Clin Epidemiol 2011](https://pubmed.ncbi.nlm.nih.gov/21775104/)）；
  非 Therapy 类 Narrow 并非 Broad 子集，建议两档合并
  （[JMLA](https://jmla.pitt.edu/ojs/jmla/article/view/589)）。
  → 本项目不内置过滤器（用户检索式已可写 `AND therapy/narrow[filter]`），但在 SKILL
  里把"研究设计"列为分档依据，并在 usage 中给出写法。
- **LLM 标题/摘要初筛的召回不稳定**：Dai et al. JMIR 2025 汇总敏感度 0.73、特异度 0.99，
  提示词修订后敏感度可到 0.98 但置信区间很宽（[JMIR 2025;27:e67488](https://www.jmir.org/2025/1/e67488)）。
  → 日报场景"漏掉一篇必读"比"多扫一眼"代价大：SKILL 规定拿不准时就高不就低
  （放 worth_a_look 而不是 skip），且 skip 只用于"仅字面命中"。

## 3. 本项目差距与对应改动（v0.2.0）

| 差距（与谁对比） | 证据 | 改动 |
| --- | --- | --- |
| retmax 在去重**之前**截断：已读文献占满名额，窗口内其余新文献永远不出现 | 实测：命中 94、去重后 87，改前首跑 17 篇、复跑 **0 新增**；v0.1.1 回归把这个 0 当成"去重生效" | esearch 取足 ID（`id_limit` 默认 1000）→ 先与 seen 去重 → 再按 retmax 截取；超出部分**顺延**、不写 seen，日报明示顺延篇数 |
| 排序用出版日期，与 edat 窗口口径不一致（My NCBI/PubMed 默认按入库） | PubMed Help "Most Recent"；实测 pub_date 排序首位是出版日期 "2026 Dec" 的提前定档条目 | 不传 sort，用默认 Most Recent；改后首跑候选近 2 天入库占比 41%→72% |
| 固定 reldate，几天没跑就漏（My NCBI 记住上次取新） | My NCBI What's New 机制 | 读 seen.updated，距上次 > reldate 时自动补窗到 gap+1 天（上限 60），可关 |
| 检索式被 PubMed 静默放宽无人知晓 | 实测 `biomarkr` 被丢弃，命中从数十变 312 | 记录 querytranslation 与告警，终端 `[warn]` + 日报 ⚠️ 显示实际执行的检索式 |
| 撤稿/勘误/预印本混在候选里无标识（研究诚信） | 实测 30 天勘误 2,121、预印本 1,810、撤稿声明 281 | 解析出版类型与 CommentsCorrections，输出 `flags`，日报徽标；SKILL 规定已撤稿不入必读、预印本须注明未经同行评审 |
| 网络瞬断/429 直接失败 | 实测 SSL EOF；NLM 429 说明 | 429/5xx/网络错误最多重试 2 次（2s、5s，尊重 Retry-After） |
| 抓取即写 seen：定时任务抓了但没来得及分档，下一次抓取会覆盖候选清单，文献永久丢失 | v0.1.x usage 推荐 cron 抓取、人工触发分档 | `--no-commit` + `render_digest.py --commit-seen`：日报成功落盘才标记已读 |

## 4. 调研后决定**不改**的点

| 点 | 理由 |
| --- | --- |
| 影响因子/分区过滤（Stork、medpapers-daily） | JCR/Scopus 为商业授权数据，需额外 key；影响因子与单篇质量相关性弱，研究设计更可靠 |
| 向量相似度/训练式推荐（zotero-arxiv-daily、LitSuggest、Scholar Inbox） | 需要用户文库或正负例，冷启动成本高；本项目目标是零配置本地运行。**反馈闭环**是下一步最有价值的方向，暂记为已知限制 |
| 防抄袭阈值 25 词 | 未找到针对"一句话导读"的阈值依据；中文导读几乎不可能与英文摘要出现 25 词连续重合，此门槛只防直接粘贴英文原文；"整句翻译"由 SKILL 规则与人工约束 |
| 用 crdt 代替 edat | crdt 会带入出版超 1 年才补录的旧文；edat 的设计正是"新近可用" |
| efetch 改 POST | 每批 100 个 PMID 的 GET URL 远低于长度限制，无收益 |

## 5. 首轮（2026-09-19）调研保留结论

- PubMed 收录 >4,000 万条引文；einfo 2026-11-02 实测 41,379,710 条。
- 2026-09-19 实测 `journal article[pt]` 最近 1 天新增 7,773–8,595 条。
- Stork 学术个人全套餐挂牌 ¥8,998/年（促销 ¥3,699–3,999），"文献导读"为付费功能——
  该价格为首轮记载，2026-11-02 官网首页未列价格，未能复核。
- "50 个关键词上限"是 Stork 免费档的限制，不是 My NCBI 的。
- Elicit Pro（$49/月）含 10 个 research alerts；Readwise Reader 无 PubMed 语义。
  （首轮记载，本轮未复核价格）
