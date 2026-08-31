# B 层：两路召回、加权 RRF、归一化分数、可插拔重排

B 层没有 SQL。它查已经写好的 LanceDB：`artifacts/corpora/default/corpus.lance`（兼容镜像 `artifacts/corpus.lance`）。表结构以 [CHUNKING.md §8 / §11](../../vault/tier_b_prose/CHUNKING.md) 为准，检索侧不要另发明列。

对应脚本：[`tier_b.py`](../tier_b.py) 管召回与融合；[`rerank.py`](../rerank.py) 只管 `RerankFn`。k 与权重只来自 YAML，见 [config.md](config.md)。

---

## 1. 建库和查询必须配对

| 侧 | API | 送进模型的字符串 |
| --- | --- | --- |
| 建库（已经跑完） | `TextEmbedding.passage_embed(...)` | `embedding_text = " > ".join(heading_path) + "\n\n" + body` |
| 查询 | `TextEmbedding.query_embed(...)` | **query 字符串本身**。不要给 query 拼 `heading_path` 前缀 |

- 模型名固定 `BAAI/bge-small-en-v1.5`，384 维。换模型 = 整表作废。
- **禁止**对这份 corpus 使用 `embed()`，禁止把 `embed()` 和 `passage_embed` / `query_embed` 混用。
- 用 `prose_preprocessing_util.bge.get_text_embedding()` 拿同一个单例。不要在 Lance 表上再挂另一套 embedding function。
- 实现时禁止 `import rag.build` 除「拿同一 bge 单例」以外的路径；单例函数最终应可从运行时依赖到达（实现轮再收口）。

router 传给 `query_prose` 的 `text` 优先级写死：

```text
query.error_text  →  若没有，则 query.query_text  →  若还没有，则把 symbols 用空格拼起来
```

版本过滤必须做在 Lance 的 `where` 里：`since_version_code <= :target`。与 A 层同一枚 `target_version_code`，同一份 `version_to_code()`。不要查完再在 Python 里筛。

---

## 2. 为什么两路独立查，不调用 Lance 内部 hybrid

YAML 要控**每一路的 k 和权重**。Lance 自带 hybrid 往往不透明。协议规定：

1. FTS / BM25 一次，`limit = bm25.k`（默认 3）
2. 向量一次，`limit = vector.k`（默认 10）
3. Python 里做加权 RRF

`channels=bm25` 或 `vector` 时只跑对应一路，融合退化成单列表，归一化仍用「这一路的理论上界」。

---

## 3. 流水线（默认值）

```text
BM25 k=3  ──┐
            ├─ 加权 RRF ─ 取前 recall_k=10 ─ 上界归一化到 [0,1]
向量 k=10 ──┘                                      │
                                    score_threshold（默认关闭）
                                                   │
                                         RerankFn（默认 identity）
                                                   │
                                         取前 rerank_k=3 → ProseHit
```

### 3.1 加权 RRF

```text
s(d) = Σ_i  w_i / (rrf_k + rank_i(d))
```

- `rank_i` 从 1 开始。只在一路出现则另一路贡献为 0。
- `rrf_k` 默认 60。`w_i` 默认 1.0 / 1.0。
- 等权 + `rrf_k=60` = 教科书 RRF。

### 3.2 上界归一化（给 Agent 的 `score`）

不用 per-query min-max（那样每条 query 的第一名都是 1.0，阈值跨 query 没有意义）。

工业常用：**用 RRF 的理论上界做除数**。

```text
s_max = Σ_i  w_i / (rrf_k + 1)
score = clip( s(d) / s_max , 0, 1 )
```

含义：

- 两路都排第 1 → `score = 1.0`
- 等权下只在一路排第 1 → `score = 0.5`
- 名次靠后 → 接近 0

这个 0～1 的数写入 `ProseHit.score` 和 `UnifiedHit.score`（B 层那几条）。**可以**做全局阈值和直方图；**不可以**和 A 层的 `1.0 / 0.7` 比。

原始 `s(d)`、分路名次只进 `on_fusion` 事件，不进 Agent 契约。

### 3.3 阈值

`score_threshold` 为 `null`：不截断（默认）。

非空：丢掉 `score < threshold` 的候选，发生在重排**之前**。截的是归一化 RRF，不是重排分。

### 3.4 重排接口（对 retriever 透明）

```python
RerankFn = Callable[[str, Sequence[ProseChunk]], Sequence[float]]
# (query_text, candidates) -> 与 candidates 等长的分数；越高越相关
```

「chunk → 分数」是逐条语义；一次传入整表，是为了 cross-encoder 能看见 query。

- YAML `reranker` 只是注册名。工厂返回 callable。
- 模型路径、batch、device、温度全部闭包在 callable 内。`query_prose` 只排序 + 截 `rerank_k`。
- 已注册：`identity`（默认，保持融合顺序）；`minilm_l6`（`Xenova/ms-marco-MiniLM-L-6-v2`，fastembed ONNX，约 80MB）。
- **返回给 Agent 的 `score` 永远是 3.2 的归一化 RRF。** 重排只改顺序。重排分只进 `on_rerank`。

禁止：在 `tier_b.py` 里 import 某个具体 cross-encoder 并写死超参。

`match_reason`：只出现在 BM25 → `bm25`；只出现在向量 → `vector`；两路都有 → `hybrid`。

---

## 4. `ProseChunk` / `ProseHit`

`ProseChunk` 已在 `schemas.py`，与 Lance 列对齐（`vector` 列不进模型）。

| 字段 | 含义 |
| --- | --- |
| `id` | 稳定 chunk id。评测用它，不用行号 |
| `text` | body，不含 heading 前缀。Agent 读这份 |
| `heading_path` | 标题路径 |
| `since_version` / `since_version_code` | 过滤只靠 code；无版本则为 0，总能过门 |
| `related_symbols` | 展示用。`query_prose` 不要拿它做 WHERE |
| `source` / `source_file` / `source_url` | 溯源 |

`ProseHit.score`：见 3.2。不要改字段名、不要加 `score_raw` 到 Agent 出参。
