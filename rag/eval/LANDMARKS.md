# 检索质量评测：实现路标

[全项目执行顺序](../../LANDMARKS.md) · [全项目问题总账](../../DEFECTS.md) · [上级文档](../LANDMARKS.md) · [本级问题](DEFECTS.md)

更新：2026-10-17。以当前代码为现状；下文未勾选项均为待修复/待开发。**按根目录 S00→S25 执行，到本目录时再展开；本级编号不重新从 1 开始。**

## 这个目录测检索，migration_agent/eval 测整次迁移

已有 `run_eval.py` 和 A/B 各 30 条查询。不要为修配置随意重生成已冻结真值；新增测试集另存版本，保留来源与规则/语料指纹。

`Prec_GT@K` 的既有公式为 `|GT∩topK|/|GT|`，正文明确命名 GT 覆盖/Recall；MRR 是第一个相关结果排名的倒数，K 内未命中记 0。不要把该指标解释成常规分母为 K 的 Precision。

S21 每个 A/B 分支分别记录计算时间与 fresh/reused；`--a-only` 复用 B 时链接到原 run，不能给它伪造当次耗时。保存逐查询相关 ID、检索 ID、策略与得分，汇总报告必须可独立重算。

BM25/vector/hybrid、identity/重排的比较使用相同冻结集合和预算；调参集合与最终测试集合分开。

## 将已有分数连接到调用链

历史报告是本地可复算证据，不能仅因接入平台就改写成新实验。S21 将同一 query/item 的 GT 覆盖率和 MRR、返回 ID、配置/语料指纹、fresh/reused 来源交给宿主评测适配器，关联 Langfuse/Phoenix 的实验和 trace/span。隐藏参考不进入 Agent 工作区或普通 span；平台评分与本地 JSONL 应逐项一致，详见 [观测契约](../../migration_agent/trace/LANDMARKS.md#otel-contract)。

## 本目录执行清单

<a id="s21"></a>

### S21：扩展变异、复验 RAG 并接入平台实验

- [ ] 完成 [S21](../../LANDMARKS.md#s21) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：保留可独立重算的 A/B 指标和 fresh/reused 来源；将结果交宿主 eval 适配到 Langfuse/Phoenix 的同一实验清单，RAG 内不另跑一套 Judge。

**交付物**：交付逐查询相关/返回 ID、配置/语料指纹及检索 span 的关联；约定 Prec_GT 为 GT 覆盖率，不写成传统 Precision。

**验收**：复用指向原 run；版本不匹配不拼接；本地与平台的 GT 覆盖/MRR 一致，重复上传不重复评分。

**问题详情与复现**：[RAG-04 · 历史复用和指标命名容易把旧结果说成新实测](DEFECTS.md#rag-04)。

## 完成一项怎么记

在相关 DEFECTS 条目附测试名称/命令、实际结果与版本；只勾本步验收通过的项目。涉及代码的目录同步 README。L3 草稿放本地 DESIGN_NOTES；跨模块有后果的决定落 docs/adr。文档修订完成不等于业务修复完成。
