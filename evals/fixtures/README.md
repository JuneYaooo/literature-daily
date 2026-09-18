# 评测夹具（全部合成）

本目录所有数据均为**人工编造的合成样本**，不含任何真实论文、真实患者或真实 API 密钥。
PMID 99010001–99010005 不指向真实文献（9xxxxxx 段为占位编号），标题、作者、期刊、
摘要、DOI 全部虚构。

| 文件 | 用途 |
| --- | --- |
| `offline_v1/esearch_kw{1,2,3}.json` | 三个关键词的 esearch 离线响应（含跨关键词重叠 PMID，模拟真实命中结构） |
| `offline_v1/efetch_v1.xml` | 6 篇合成"文献"的 efetch XML，覆盖边界：无 DOI（99010002）、无摘要（99010003）、作者名带后缀 Jr（99010001）、集体作者（99010004）、结构化摘要与 MedlineDate（99010003/99010004）、标题含斜体标记（99010002）、图书章节 PubmedBookArticle（99010006，回归自真实运行缺陷） |
| `config_offline_v1.json` | 离线评测配置：3 关键词、retmax=4、reldate=7 |
| `seen_partial_v1.json` | 已看seen 场景：初始只有 99010002，验证部分去重与原子写回 |
| `verdicts_good_v1.json` | 合规导读样例：中文一句话均为改写，含 skip 档（不写导读） |
| `verdicts_plagiarism_v1.json` | 坏样例：99010001 的 one_liner 逐字照抄摘要开头 30 词，验证渲染器以退出码 4 拒绝 |

版权口径与线上行为一致：真实运行中抓取的摘要只用于本地 Agent 阅读与分档，
入库的评测产物一律 `--strip-abstract` 去摘要或只含改写后的一句话导读。
