# 运行时配置操作手册

权威文件是与脚本同目录的 [`retriever.yaml`](../retriever.yaml)。本文告诉你**改哪、会怎样、评测怎么覆盖、和 Agent 契约怎么分开**。键的语义以 YAML 注释和本文为准；不要在 `RetrievalQuery` 里平行发明一套。

加载函数签名见 [`config.py`](../config.py) 模块 docstring。本轮该文件只有 stub，没有解析实现。

---

## 1. 先记住三件事

1. **管道内部只认 YAML**（或实现后的 `RetrieverConfig` 对象）。权重、`recall_k`、BM25 的 `k`、通道、阈值、重排名都不进 `RetrievalQuery`。
2. **生产 Agent 不要传 `top_k`。** Pydantic 契约里这个字段默认仍是 `8`（为了不改 Agent JSON Schema）。若 Agent 显式带上默认值，会和 YAML 的 `rerank_k: 3` 打架。正确用法：工具调用只填 `error_text` / `symbols` / `target_version`；条数交给 YAML。
3. **改了会影响召回的键必须进 `config_hash`。** 否则 Redis 会把旧权重下的答案当成新配置的答案。见 [docs/hash_and_manifest.md](../../../docs/hash_and_manifest.md)。

---

## 2. 文件在哪、谁读

| 项 | 值 |
| --- | --- |
| 路径 | `rag/retriever/retriever.yaml`（与 `tier_a.py` 等脚本同目录） |
| 谁读 | 仅 `config.load_config()`。router / tier_b 拿已经 load 好的对象，自己不再打开文件 |
| 谁不读 | Agent、LangGraph 工具函数、`tier_a.query_rules()` |
| 进不进 wheel | 实现时应打进 `rag.retriever` 包数据；本轮只把文件放在源码树 |

进程启动 load 一次，后续检索复用。评测需要换参数时：复制一份 YAML，或 `RetrieverConfig` 拷贝后改字段，再传入 `retrieve()` / `run_ablation.py`，不要改 Agent 入参模型。

---

## 3. 每个键改了会影响哪一步

### `tier_a.top_k`

- 默认 `8`。
- 影响：A 层 SQL 的 `LIMIT`。
- 不影响：B 层任何一步、RRF、重排。
- 覆盖：`RetrievalQuery.top_k_a` 非空时，用它当 LIMIT。

### `tier_b.channels`

- 取值：`hybrid`（默认）/ `bm25` / `vector`。
- 影响：B 层开哪几路。`bm25` 只跑关键词；`vector` 只跑向量；`hybrid` 两路都跑再 RRF。
- **不是** `RetrievalMode`。`RetrievalMode` 管的是「这次调不调 A、调不调 B」。
- 评测阶段 A 只扫这个键，其余保持默认。

### `tier_b.bm25.k` / `tier_b.vector.k`

- 默认 BM25 `3`、向量 `10`。
- 影响：各路从 Lance **先取出多少条**，在融合之前。
- 关键词 k 故意收小：符号精确匹配不需要 8 条噪声。上线后再用矩阵扫描优化。

### `tier_b.bm25.weight` / `tier_b.vector.weight`

- 默认都是 `1.0`（等权 = 经典 RRF）。
- 影响：加权 RRF 里这一路的系数。负值非法，`load_config()` 应直接失败，不要夹成 0。
- 第一阶段评测不扫权重。

### `tier_b.fusion.method` / `tier_b.fusion.rrf_k`

- 目前只允许 `rrf`。`rrf_k` 默认 `60`（Cormack et al.）。
- 影响：融合公式 `s(d) = Σ_i w_i / (rrf_k + rank_i(d))`。
- 第一阶段不扫 `rrf_k`。

### `tier_b.recall_k`

- 默认 `10`。
- 影响：融合排序后、重排前保留多少条。矩阵扫描的一个轴。

### `tier_b.rerank_k`

- 默认 `3`。
- 影响：重排后交给 Agent 的 B 层条数。矩阵扫描的另一个轴。
- 覆盖：`RetrievalQuery.top_k_b` 非空时，用它当最终 B 层条数（重排截断），**不**改变 `recall_k`。

### `tier_b.score_threshold`

- 默认 `null` = **不截断**。
- 非空时：在 RRF 上界归一化之后、重排之前，丢掉 `score < threshold` 的候选。
- `score` 是 `[0, 1]`，见 [tier-b.md](tier-b.md)。

### `tier_b.reranker`

- 默认 `identity`。只是注册名，由 `rerank.py` 的工厂映射到 callable。
- 已注册：`identity`；`minilm_l6`（`Xenova/ms-marco-MiniLM-L-6-v2`，fastembed）。模型路径 / batch 闭包在 callable 内，YAML 不再为每种重排加键。
- 换重排方案：把这里改成已注册名，或评测脚本直接把 callable 传给 `query_prose()`。生产默认先保持 `identity`，评测对比用 `RetrieverConfig` 副本。

### `observability.log_dir` / `observability.sample_rate`

- `log_dir` 默认相对 `rag/` 的 `artifacts/logs/retriever`（gitignore）。
- `sample_rate` 默认 `0.0`：不把 `on_retrieve_end` 交给非 NoOp sink；**hook 函数本身仍被调用**（NoOp）。见 [observability.md](observability.md)。

---

## 4. 优先级（实现必须按此解析）

最终 A 层 LIMIT：

```text
query.top_k_a 非空  → 用它
否则 YAML tier_a.top_k
否则（YAML 缺失时的兜底）query.top_k
```

最终 B 层条数（重排后）：

```text
query.top_k_b 非空  → 用它
否则 YAML tier_b.rerank_k
否则（YAML 缺失时的兜底）query.top_k
```

B 层管道内部（`bm25.k`、`vector.k`、权重、`recall_k`、通道、阈值、reranker、`rrf_k`）：

```text
只认 YAML / RetrieverConfig。RetrievalQuery 碰不到。
```

`query.top_k` 留在契约里，是为了 Agent JSON Schema 不删字段，以及「忘了放 YAML 的开发环境」还能跑。生产路径以 YAML 为准。

---

## 5. 怎么改：三个场景

### 生产：只改 YAML 默认值

打开 `retriever.yaml`，例如把向量一路权重大一点：

```yaml
tier_b:
  vector:
    weight: 2.0
```

存盘后 **重启 worker**（配置进程内 load 一次）。`config_hash` 变了，旧缓存自然打不中。

不要在 LangGraph 工具参数里加 `vector_weight`。

### 评测阶段 A：三通道，k 锁死

不要改 k。只扫 `channels`：

```python
# 示意：实现后的用法。本轮 run_ablation.py 只有 docstring。
for ch in ("bm25", "vector", "hybrid"):
    cfg = base_config.model_copy(update={"tier_b": {**base.tier_b, "channels": ch}})
    run_queries(cfg)
```

或准备三份 YAML 副本，只改 `tier_b.channels`。

### 评测阶段 B：k 矩阵

通道已选定。复制 config，扫：

```text
recall_k ∈ {5, 10, 20}
rerank_k ∈ {1, 3, 5}
```

权重、`rrf_k`、真重排模型不进这一轮。详见 [eval.md](eval.md)。

---

## 6. 非法值

`load_config()` 应直接失败，不要默默夹紧：

- k 不在 1～50
- 权重为负或非数字
- `channels` 不是 `hybrid` / `bm25` / `vector`
- `fusion.method` 不是 `rrf`
- `score_threshold` 既不是 `null` 也不在 `[0, 1]`
- `sample_rate` 不在 `[0, 1]`
- `reranker` 未注册

校验失败发生在启动或评测加载配置时，不要等到第一次 `retrieve()` 才炸一半。

---

## 7. 与 `RetrievalMode` 的分工

| 旋钮 | 在哪 | 管什么 | 谁用 |
| --- | --- | --- | --- |
| `RetrievalQuery.retrieval_mode` | Agent / 评测 Query | 开不开 A 层、开不开 B 层：`hybrid` / `exact_only` / `semantic_only` | 「只有字典 / 只有散文 / 两层都要」 |
| `tier_b.channels` | YAML | B 层内部：纯 BM25 / 纯向量 / 两路 RRF | 「纯关键词 vs 纯向量 vs 混合」Recall@5 |

两套名字都叫过 hybrid，不要混。docs/rag.md 要的那张对比表，对应的是 **`channels`**，不是 `RetrievalMode`。

---

## 8. 缓存指纹

```text
cache_key = sha256(manifest_hash + ":" + config_hash + ":" + query_json_without_request_id)
```

`config_hash` 至少包含：`tier_a.top_k`、`tier_b.channels`、两路 `k`/`weight`、`fusion.*`、`recall_k`、`rerank_k`、`score_threshold`、`reranker`。不含 `request_id`、不含 `log_dir`（日志路径不应拆开缓存槽）。`sample_rate` 建议也不进指纹：它不改变返给 Agent 的 hits。

实现 `config_hash()` 时用稳定序列化（排序键、固定小数）。见 [`cache.py`](../cache.py) 与 [hash_and_manifest.md](../../../docs/hash_and_manifest.md)。
