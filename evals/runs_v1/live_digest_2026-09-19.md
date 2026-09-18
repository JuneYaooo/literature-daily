# 医学文献日报 · 2026-09-19

> 候选 17 篇（已去重）｜🔴 必读 3 ｜🟡 值得扫一眼 7 ｜⚪ 可跳过 7
> 研究方向：脓毒症（sepsis）生物标志物、ICU 机器学习早期预警评分，以及可在床旁落地的预测模型验证研究

## 🔴 必读（与研究方向强相关，建议点开读原文）

### 1. [Dynamic Changes of Neutrophil Nuclear Membrane CD63 as a Potential Biomarker for Early Adjunctive Diagnosis and Prognostic Evaluation of Sepsis in Critically Ill Patients: A Prospective Cohort Study.](https://pubmed.ncbi.nlm.nih.gov/42756472/)
`MedComm (2020) · 2026 Oct · DOI: 10.1002/mco2.71007` · Xingxin Gao, Min Zhang, Linbin Li 等
- **导读**：中性粒细胞核膜 CD63（nmCD63）流式检测在两中心前瞻队列（含独立外部验证）中可早于常规指标提示脓毒症并评估预后。
- **理由**：正中研究方向：全新脓毒症早诊生物标志物，且带外部验证的前瞻设计，方法学与我们课题直接可比。

### 2. [AI-Based Sepsis Prediction in Hospitalized Adults: Systematic Review, Subgroup Meta-Analysis, and Contextual Analysis of Clinical Burden.](https://pubmed.ncbi.nlm.nih.gov/42753195/)
`J Med Internet Res · 2026 Sep 17 · DOI: 10.2196/95665` · Gyeong Min Lee, Joo-Yun Won, Eun Young Cho 等
- **导读**：对住院成人 AI 脓毒症预测模型的系统综述与亚组荟萃分析：按预测窗口与验证成熟度拆解后，报告的性能异质性仍然很大。
- **理由**：做 ML 预警研究必看的证据全景，可直接用作我们模型验证设计与报告规范的对照基准。

### 3. [Automated CT-derived visceral-to-subcutaneous fat ratio as a prognostic imaging biomarker for mortality in sepsis.](https://pubmed.ncbi.nlm.nih.gov/42736406/)
`Eur Radiol · 2026 Sep 14 · DOI: 10.1007/s00330-026-12877-x` · Lin Fu, Xinyi Chen, Songqiao Liu 等
- **导读**：nnU-Net 自动分割 CT 内脏/皮下脂肪比，在 1716 例多中心脓毒症队列（含外部队列）中用五种机器学习生存模型验证了死亡预后价值。
- **理由**：影像组学标志物 + 机器学习 + 外部验证的组合与本研究路线高度一致，可参考其生存建模方案。

## 🟡 值得扫一眼（可能相关，扫标题与导读即可）

### 4. [Persistent elevation of procalcitonin following resolution of presumed community-acquired pneumonia revealing sporadic medullary thyroid carcinoma.](https://pubmed.ncbi.nlm.nih.gov/42750968/)
`Arch Clin Cases · 2026 · DOI: 10.22551/2026.52.1303.10346` · Shin Yee Tang, Shaikh Abdul Matin Mattar
- **导读**：病例报告：肺炎治愈后降钙素原持续升高，最终查出甲状腺髓样癌，提示非感染性 PCT 升高的鉴别陷阱。
- **理由**：生物标志物解读的临床警示，但为个案证据，级别有限。

### 5. [Pathological Signal-Responsive Nanoplatforms for Sepsis: Integrating Biomarker Sensing With Spatiotemporal Drug Delivery and Immunomodulation.](https://pubmed.ncbi.nlm.nih.gov/42750136/)
`Adv Sci (Weinh) · 2026 Sep 16 · DOI: 10.1002/advs.77718` · Yukun Liu, Kang Wang, Kwet Kyawl Yan 等
- **导读**：综述“生物标志物触发”的智能纳米平台：感知脓毒症微环境 pH/ROS/酶异常后按时空释放药物并免疫调节。
- **理由**：标志物 sensing 与治疗结合的前沿方向，可启发标志物临床转化的新思路。

### 6. [Unravelling Ferroptosis in Sepsis: A Comprehensive Integrative Transcriptomic Analysis Across Age and Disease Severity.](https://pubmed.ncbi.nlm.nih.gov/42756334/)
`Bioinform Biol Insights · 2026 · DOI: 10.1177/11779322261447645` · Miguel Victor Bringel Sales, Helder Imoto Nakaya, Fernando de Queiroz Cunha 等
- **导读**：整合 17 套转录组数据（bulk + 单细胞）分析脓毒症中铁死亡的调控图谱，及其随年龄与病情严重度的变化。
- **理由**：铁死亡可能产出新的分型/预后标志物，数据驱动的整合分析值得跟进。

### 7. [MEDAL: Sequential adapter learning for privacy-preserving multicenter clinical language models.](https://pubmed.ncbi.nlm.nih.gov/42753937/)
`J Biomed Inform · 2026 Sep 17 · DOI: 10.1016/j.jbi.2026.105101` · Ahmed Bakr, Augusto Garcia-Agundez, Travis Atkison 等
- **导读**：MEDAL 框架在不转移患者数据的前提下顺序微调 LLM 适配器，跨医院训练临床笔记模型（含脓毒症出院诊断任务）。
- **理由**：多中心隐私保护建模方法，对我们未来跨院协作训练预警模型有直接参考价值。

### 8. [Machine Learning-Based Prediction of Culture-Confirmed Neonatal Sepsis in a Tertiary Neonatal Intensive Care Unit: Retrospective Cohort Study.](https://pubmed.ncbi.nlm.nih.gov/42735002/)
`JMIR Med Inform · 2026 Sep 14 · DOI: 10.2196/88732` · Eman Badran, Oraib Al-Smadi, Loiy T Algazo 等
- **导读**：约旦三级 NICU 用结构化 EHR 数据做机器学习预测血培养确诊新生儿脓毒症的回顾性队列。
- **理由**：人群不同（新生儿）但任务同构，可关注其在低资源场景的特征工程与性能取舍。

### 9. [Performance of Pediatric Early Warning Score and physician gestalt in predicting adverse events among critically ill patients in an Emergency Department in Tanzania.](https://pubmed.ncbi.nlm.nih.gov/42751431/)
`Afr J Emerg Med · 2026 Dec · DOI: 10.1016/j.afjem.2026.101008` · Irene A Kindole, Humphrey G Medarakini, Alphonce N Simbila 等
- **导读**：坦桑尼亚急诊前瞻队列：儿科早期预警评分（PEWS）与医生直觉预测危重不良事件的头对头比较。
- **理由**：EWS 与人工判断的比较证据多来自高收入国家，低资源场景数据可补全外部效度视野。

### 10. [Association between early prehospital administration antibiotic and 28-day mortality in sepsis.](https://pubmed.ncbi.nlm.nih.gov/42742186/)
`Prehosp Emerg Care · 2026 Sep 15 · DOI: 10.1080/10903127.2026.2733964` · Karn Suttapanit, Pannita Deeiad, Siriporn Damdin 等
- **导读**：院前经验性抗生素与疑似脓毒症患者 28 天死亡率的观察性队列关联分析。
- **理由**：早期识别与给药时间窗是预警模型的下游收益指标，结果可用于论证落地价值。

## ⚪ 可跳过（仅字面命中，不写导读）

- 11. [Incidence and risk factors for postpartum infections: A Norwegian cohort study, 2012-2020.](https://pubmed.ncbi.nlm.nih.gov/42757709/) — Acta Obstet Gynecol Scand · 2026 Sep 18 · DOI: 10.1111/aogs.70355 · 命中：sepsis biomarker

- 12. [Artificial intelligence and machine learning in transplantation surgery care pathway.](https://pubmed.ncbi.nlm.nih.gov/42751007/) — World J Transplant · 2026 Sep 18 · DOI: 10.5500/wjt.122433 · 命中：sepsis biomarker、machine learning sepsis

- 13. [Bridging machine learning and evolutionary optimization of threshold specific dosages of Nisin to suppress MRSA biofilm.](https://pubmed.ncbi.nlm.nih.gov/42752685/) — Antonie Van Leeuwenhoek · 2026 Sep 17 · DOI: 10.1007/s10482-026-02423-6 · 命中：machine learning sepsis

- 14. [Research on Risk Classification of Online Public Opinion in Emergencies Based on FHCO Algorithm.](https://pubmed.ncbi.nlm.nih.gov/42755392/) — Risk Anal · 2026 Oct · DOI: 10.1111/risa.70358 · 命中：early warning score

- 15. [From Plan to Practice: Embedding Safety Planning in Inpatient Mental Health Care.](https://pubmed.ncbi.nlm.nih.gov/42725545/) — Int J Ment Health Nurs · 2026 Oct · DOI: 10.1111/inm.70345 · 命中：early warning score

- 16. [Comparison of Performance of Publicly Available Polygenic Risk Scores to Predict Clinically Actionable Coronary Artery Calcium Scores: The BioHEART-CT Cohort.](https://pubmed.ncbi.nlm.nih.gov/42747424/) — Eur J Prev Cardiol · 2026 Sep 16 · DOI: 10.1093/eurjpc/zwag480 · 命中：early warning score

- 17. [Laboratory Evaluation of Sepsis](https://pubmed.ncbi.nlm.nih.gov/37603649/) — 图书条目 · 无 DOI · 命中：early warning score

## 统计

| 关键词 | 近 7 天命中 | 取回 |
| --- | --- | --- |
| sepsis biomarker | 33 | 6 |
| machine learning sepsis | 12 | 6 |
| early warning score | 14 | 6 |

- 窗口内命中共 59 篇；本轮去重前 17 篇，已看过跳过 0 篇，实际收录 17 篇。
- 版权说明：本日报只含一句话导读、链接与元数据，不含摘要原文；全文请点击链接到 PubMed/出版方阅读。导读为 AI 生成，仅供筛读参考，结论以原文为准。
