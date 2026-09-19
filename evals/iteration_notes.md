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

## 已知限制（未在本次修复）

- 相关性分档与中文导读是 AI 生成（model_only 自评），未经医学信息学背景的人工复核；
  导读仅供筛读，结论必须回到原文。
- 增量窗口用 `datetype=edat`：in-process 记录状态变化会使同一篇在窗口内"重见"，
  目前靠 seen 集合兜底；如遇 NCBI 故障漏发，次日窗口仍为固定 reldate，不做回溯重叠
  （My NCBI 的做法是下期补发），连续多日不跑的用户建议临时调大 reldate。
- 宽泛检索式单日可命中数千条：retmax 只截取最新 N 篇，超出部分静默不取（日志里有
  命中数 vs 取回数，可发现截断），未做翻页全量拉取。
- 一次只处理一个 config；多账号/多方向订阅需分别运行。
