# RAG Retriever 离线评测报告
生成时间: 2026-08-31 10:35:53
总耗时: 0.07s
可视化页：[`eval_report.html`](eval_report.html)
## 实验设计
- 粗召回锁定 `bm25.k=vector.k=20`，权重 **0.3:0.7**，`recall_k=20`。
- 对照：`identity`（RRF 原序）vs `minilm_l6`（`Xenova/ms-marco-MiniLM-L-6-v2`）。
- 两路都对融合后的 20 条重排，再截 `rerank_k ∈ {2,3,5}`。
- **Prec_GT@K** = |GT ∩ top-K| / |GT|。**MRR** 在前 K 条上算。
## A 层 Recall
| K | mean Recall@K |
| --- | --- |
| 5 | 0.8833 |
| 8 | 0.9233 |
| 15 | 0.9933 |
- @5 未满：a_0011, a_0014, a_0017, a_0018, a_0025, a_0027, a_0029；@8 未满：a_0011, a_0017, a_0025, a_0027；@15 未满：a_0025
- 不采纳 @4（0.840）：那一档被 `|GT|=5` 的理论上限 0.8 污染。@5 上限是 1.0，相对 @8 只掉 0.040。多出来的 3 条（`a_0014/0018/0029`）都是 4/5，第 5 条 GT 落在 6–8。真正排序不够的仍是 `a_0011/0017/0025/0027`。生产 `tier_a.top_k=8` 不用改。
## B 层：identity vs minilm_l6
| K | Prec_GT id | Prec_GT mini | ΔPrec | MRR id | MRR mini | ΔMRR |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 0.8333 | 0.7833 | -0.0500 | 0.8500 | 0.8000 | -0.0500 |
| 3 | 0.9000 | 0.8833 | -0.0167 | 0.8722 | 0.8444 | -0.0278 |
| 5 | 0.9667 | 0.9000 | -0.0667 | 0.8722 | 0.8444 | -0.0278 |
## 第一命中对照
| 指标 | identity | minilm_l6 |
| --- | --- | --- |
| 平均第一命中（未命中按 21） | 1.30 | 1.40 |
| 改了 top-1 | — | 8/30 |
| 第一命中提升 / 下降 / 不变 | — | 3 / 5 / 22 |
名次变化明细：
| gt_id | kind | identity 名次 | minilm 名次 |
| --- | --- | --- | --- |
| b_0000 | semantic | 2 | 1 |
| b_0003 | semantic | 1 | 3 |
| b_0004 | error | 2 | 1 |
| b_0007 | semantic | 2 | 3 |
| b_0012 | error | 1 | 2 |
| b_0021 | semantic | 3 | 2 |
| b_0026 | error | 2 | 3 |
| b_0028 | semantic | 1 | 2 |
## 结论
**结论：生产保持 `identity`，不要上 MiniLM。** 粗召回 RRF 已经把 GT 排得很靠前；cross-encoder 改序的净效果是负的，会把部分已在前 3 的 GT 挤出短名单。
- K=3（生产默认短名单）：Prec_GT identity `0.900` → minilm `0.883`（-0.0167）； MRR `0.872` → `0.844`（-0.0278）。
- K=2：Prec_GT -0.0500， MRR -0.0500。 K=5：Prec_GT -0.0667， MRR -0.0278。
- 第一命中名次（未命中按 21）：identity 平均 1.30，minilm 1.40。 提升 3 条，下降 5 条，不变 22 条； 改了第一名 8/30。
- Prec_GT@3 逐条：提升 0，下降 1，不变 29。 变差：b_0017。
- 分 query 类型 @3：报错 Prec_GT `0.933` → `0.900`；语义 `0.867` → `0.867`。
- 耗时：identity 0.00s / 30 条， minilm_l6 0.00s / 30 条（含首次加载）。
- Prec_GT@3 唯一变差的 `b_0017` 是 composite：GT 是 gist 里两条不相关迁移（`EditorPlugin` 要 `super._ready()`，以及 `modulate`/`COLOR`）。RRF 两条都在前 3；MiniLM 主题塌缩，用同类官方 class 页挤掉第二条。
## 读表注意
- 生产 YAML 先别改，等结论落地再动 `reranker`。
- 明细：`eval/reports/eval_details.jsonl`。会话状态：`SESSION_STATE.md`。
