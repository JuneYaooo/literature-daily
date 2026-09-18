# 对标：文献追踪工具与本项目定位（2026-09-19 调研）

调研方法：公开产品主页阅读 + GitHub API 星数实查（2026-09-19）。引用版权归原作者
所有，仅作定位说明；未从任何竞品转载素材。

## 需求证据

- PubMed 收录超过 4,000 万条生物医学文献引文（[PubMed About](https://pubmed.ncbi.nlm.nih.gov/about/)）；
  本次实测 `journal article[pt]` 最近 1 天新增 7,773 条、`medline[sb]` 最近 1 天 1,827 条
  （E-utilities esearch，2026-09-19）——靠人肉刷 PubMed 不现实。
- [Stork 文献鸟](https://www.storkapp.me/)：官方博客称已被 82 篇科研论文致谢引用
  （7 国 40+ 大学）；学术个人全套餐年费挂牌 ¥8,998（促销 ¥3,699–3,999），说明
  "追踪 + 降噪 + 导读"已被市场付费验证，且中文用户是主力市场。
- Stork 的降噪本质是**规则过滤**（关键词命中 × 影响因子阈值，Pro 才可设阈值），
  付费点在"文献导读"等 AI 功能；免费档推送原始列表。

## 一个常见误传的澄清

"50 个关键词上限"**是 Stork 免费档的限制**，不是 My NCBI 的——My NCBI 官方帮助页
没有 saved searches 数量的 50 上限（旧版 NLM 文档写的是 saved searches + collections
合计 ≤100；50 只是每封邮件条数的选项之一）。本仓库用它对标时如实区分两者。

## 现有方案与差距

| 方案 | 定位 | 与本项目的差异 |
| --- | --- | --- |
| Stork 文献鸟（SaaS，¥4k–9k/年） | 关键词订阅 + IF 过滤 + 付费 AI 导读 | 收费且云端投递；本项目本地运行、零订阅费、中文导读免费，但无影响因子过滤与邮件投递 |
| My NCBI Saved Searches（免费） | 检索式保存 + 邮件推送 | 只给原始列表：无相关性降噪、无中文导读、无跨关键词去重合并，依赖邮箱可达性 |
| [Elicit](https://elicit.com/pricing)（Pro $49/月） | 系统综述与文献问答 | 定位是"回答研究问题"，不是每日关键词订阅流；Pro 才含 10 个 research alerts |
| [Readwise Reader](https://readwise.io/read)（$9.99/月起） | 通用稍后读（RSS/PDF/EPUB） | 无 PubMed 语义、无文献元数据处理、无中文导读 |
| [TideDra/zotero-arxiv-daily](https://github.com/TideDra/zotero-arxiv-daily)（5,962★，2026-09-19 实查） | 以 Zotero 文库为画像给 arXiv/bioRxiv 新论文排序 + LLM TL;DR | **数据源无 PubMed**；依赖 Zotero 库而非自选关键词；中文导读非核心 |
| paper-radar 等 PubMed 侧开源（最高 106★） | 个人文献雷达/单病种 digest | 偏个人配置或雏形；"PubMed 订阅 → 增量去重 → 语义分档 → 中文导读日报"完整链路的开源实现仍空缺 |

## 本项目立场

- 本地优先：关键词、seen 状态、日报全部在本机；NCBI 只收到检索请求本身。
- 版权克制：日报只含一句话导读、链接与元数据，不复制摘要原文（渲染器强制校验）。
- 温柔调用：默认 1.1s 间隔（约 0.9 req/s），远低于 NCBI 无 key 上限，不建 CI、不上云。
- 诚实边界：导读是 AI 生成、无影响因子数据、截断的命中不假装完整（日志明示）。
