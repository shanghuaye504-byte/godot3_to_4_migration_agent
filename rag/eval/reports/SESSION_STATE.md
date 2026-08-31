# 评测会话状态（窗口接近极限时落盘）

写于 2026-08-31。后续改 YAML、写报告、接重排模型都先读本文件。

## 已锁定（不要再扫）

- B 粗召回：`bm25.k = 20`，`vector.k = 20`，`recall_k = 20`。
- RRF 比重：**bm25 0.3 / vector 0.7**（三七开）。0.4:0.6 的 MRR 相同；1:1 的 Recall@10 更好（1.000 vs 0.983），但第一命中略差。已选 0.3:0.7。
- **不要**跑 `eval/build_eval_set.py` 覆盖 `test_tier_a/`、`test_tier_b/`。
- A 层 query：`symbols` 只有 `old_symbol`，`exact_only`。
- B 层 query：15 报错 + 15 语义，已按 chunk.text 正向对齐。
- 生产 `retriever.yaml` 的 k/权重/reranker **先别改**（测试锁了默认 identity + 旧 k）。评测用 `RetrieverConfig` 副本。

## 指标约定

- **Recall@K** = `|GT ∩ top-K| / |GT|`，30 条宏平均。
- **不要写 Precision@K（分母=K）**。|GT|≈1 时上限≈1/K，没有信息。
- **Prec_GT@K** = `|GT ∩ top-K| / |GT|`。与 Recall@K 同构。重排实验的 K 是 **`rerank_k`（交给 Agent 的条数）**。
- **MRR** = 1 / 第一条 GT 的排名；K 内未命中为 0。用户有时写成 MMR，本项目指 Mean Reciprocal Rank，不是 Maximal Marginal Relevance。

## 粗召回数字（短名单 20+20）

| bm25:vector | Recall@10 | MRR | 平均第一命中名次 |
| --- | --- | --- | --- |
| 1.0:1.0 | 1.000 | 0.856 | 1.33 |
| **0.3:0.7** | 0.983 | **0.872** | **1.30** |
| 0.4:0.6 | 0.983 | 0.872 | 1.30 |

A：Recall@5=0.883，@8=0.923，@15=0.993。**不采纳 @4**（被 `|GT|=5` 上限污染）。@5 相对 @8 掉 0.040，多出的未满是 `a_0014/0018/0029`（都是 4/5）。@8 未满仍是 a_0011/0017/0025/0027；@15 只剩 a_0025。生产 `tier_a.top_k` 保持 8。

## identity 截断基线（20+20，0.3:0.7）

| rerank_k | Prec_GT（分母\|GT\|） | MRR |
| --- | --- | --- |
| 2 | 0.833 | 0.850 |
| 3 | 0.900 | 0.872 |
| 5 | 0.967 | 0.872 |

MRR 在 K=3 已封顶。Prec_GT 随 K 升是少截断，不是重排变强。

## 已接入的真重排

- 协议：`rag/retriever/rerank.py` 的 `RerankFn`。YAML 只填注册名。模型路径 / batch 闭包在 callable 内。**禁止**在 `tier_b.py` 写死模型。
- `ProseHit.score` 永远是归一化 RRF，重排只改顺序。
- 注册名 **`minilm_l6`** → `Xenova/ms-marco-MiniLM-L-6-v2`（fastembed `TextCrossEncoder`，ONNX，约 80MB）。
- 选它的原因：粗召回已经够准，要快；同栈（fastembed + huggingface-hub + onnxruntime），不新增依赖；比 `bge-reranker-base`（1GB）和 jina turbo 更小。
- 生产 YAML **仍是 `identity`**。评测对比时在 `RetrieverConfig` 副本里写 `reranker="minilm_l6"`。
- 缓存目录与 BGE 相同：`FASTEMBED_CACHE_PATH`（本机约定 `$HOME/.cache/fastembed`）。
- 送给 cross-encoder 的 passage = `heading_path` 用 ` > ` 拼接 + 空行 + `text`，与建库 `embedding_text` 同形。

## 重排对照结论（已锁定）

identity vs `minilm_l6`，20+20、0.3:0.7：

| K | Prec_GT id | Prec_GT mini | Δ | MRR id | MRR mini | Δ |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 0.833 | 0.783 | -0.050 | 0.850 | 0.800 | -0.050 |
| 3 | 0.900 | 0.883 | -0.017 | 0.872 | 0.844 | -0.028 |
| 5 | 0.967 | 0.900 | -0.067 | 0.872 | 0.844 | -0.028 |

- 第一命中平均 1.30 → 1.40；提升 3 / 下降 5 / 不变 22；改 top-1 8/30。
- Prec_GT@3 逐条：提升 0，下降 1（`b_0017` composite，MiniLM 主题塌缩挤掉第二条 GT）。
- **生产保持 `identity`。不要改 YAML `reranker`。** 粗召回已经够准，MiniLM 净效果为负。
- 不要再扫粗召回 k、50 vs 20、或再换这个 MiniLM。若以后要真重排，必须换更贴 Godot 迁移语料的模型，并先过同一对照表。

## 入口

- 跑分：`cd rag && uv run python eval/run_eval.py`
- 脚本：`rag/eval/run_eval.py`
- 评测集：`rag/eval/test_tier_a/`、`rag/eval/test_tier_b/`
- 重排实现：`rag/retriever/rerank.py`
