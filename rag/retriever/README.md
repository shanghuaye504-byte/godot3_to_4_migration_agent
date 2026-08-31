# Retriever：给 Agent 用的 A/B 层检索

一次调用同时查 **A 层规则字典**（SQLite）和 **B 层散文**（LanceDB），订成一份结构化结果交给迁移 Agent。默认不是「A 命中就短路」。

库已经按 [build/README.md](../build/README.md) 和 [CHUNKING.md](../vault/tier_b_prose/CHUNKING.md) 建好。本包只读成品库，不改表结构。

| 你要… | 去哪 |
| --- | --- |
| 设计思路与模块边界 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 第一次把调用链走通 | [docs/tutorial.md](docs/tutorial.md) |
| 入参 / 出参字段 | [docs/contracts.md](docs/contracts.md) |
| 改 k、权重、阈值 | [docs/config.md](docs/config.md) · [retriever.yaml](retriever.yaml) |
| 挂观测 hook | [docs/observability.md](docs/observability.md) |
| 离线评测怎么扫 | [docs/eval.md](docs/eval.md) |
| 全部文档索引 | [docs/README.md](docs/README.md) |

---

## 设计思路（一页）

- Agent 填 `RetrievalQuery`（报错、符号、目标版本），**不写 SQL**。
- `tier_a.py` 里 SQL 模板写死，值走 `?`。陷阱行靠 `detection_method` 从类型上对 Agent 不可见。
- `tier_b.py` 对同一张 Lance 表跑 BM25 与向量两路，加权 RRF 融合，分数做**理论上界归一化**得到 `[0,1]`，再可选阈值、再可插拔重排。
- `router.py` 把 A 全部放前、B 全部放后。两套分数不能比。
- 调参只改同目录 YAML。观测只通过 `RetrievalObserver` 注入，默认 NoOp，避免后期没口子。

---

## 使用方法

```python
from rag.retriever import RetrievalQuery, load, retrieve_cached

# 进程启动一次：打开 rules.db、corpus.lance、读 YAML。
load()

# 生产：不要传 top_k。条数由 retriever.yaml 决定（A=8，B 重排后=3）。
result = retrieve_cached(
    RetrievalQuery(
        error_text="Invalid call. Nonexistent function 'instance' in base 'PackedScene'.",
        symbols=["instance"],
        target_version="4.7.1",
    )
)
# result.coverage / recommended_action / escalate_suggested
# result.structured_hits  — A 层规则
# result.prose_hits       — B 层段落，score ∈ [0, 1]
```

在 `rag/` 下用 uv 跑一次检索（需已 `uv sync --group build --group dev`，且存在 `artifacts/rules.db`）：

```bash
cd rag
uv run python -c "
from rag.retriever import RetrievalQuery, load, retrieve_cached
load()
r = retrieve_cached(RetrievalQuery(
    error_text=\"Invalid call. Nonexistent function 'instance' in base 'PackedScene'.\",
    symbols=['instance'],
    target_version='4.7.1',
))
print(r.coverage, r.recommended_action, [h.rule.new_symbol for h in r.structured_hits[:3]])
"
```

`exact_only` 只查 A 层，不加载 BGE。默认 `hybrid` 会走 `query_embed`，需要 `FASTEMBED_CACHE_PATH` 下已有 bge-small 缓存。

---

## 配置方法

唯一文件：[retriever.yaml](retriever.yaml)（与脚本同路径）。操作手册：[docs/config.md](docs/config.md)。

默认（也是评测阶段 A 要锁死的值）：

| 键 | 默认 | 作用 |
| --- | --- | --- |
| `tier_a.top_k` | 8 | A 层 SQL LIMIT |
| `tier_b.bm25.k` / `weight` | 3 / 1.0 | 关键词一路 |
| `tier_b.vector.k` / `weight` | 10 / 1.0 | 向量一路 |
| `tier_b.recall_k` | 10 | 融合后、重排前 |
| `tier_b.rerank_k` | 3 | 重排后给 Agent |
| `tier_b.channels` | hybrid | B 内部：bm25 / vector / hybrid |
| `tier_b.score_threshold` | null | 不截断 |
| `tier_b.reranker` | identity | 注册名。已有 `identity` / `minilm_l6` |

优先级：管道内部只认 YAML。`RetrievalQuery.top_k_a` / `top_k_b` 非空才覆盖**最终条数**。生产 Agent 不要传 `top_k`，以免契约默认 8 盖掉 `rerank_k=3`。

改权重或 k 之后必须换缓存槽：`cache_key` 含 `config_hash`。非法值在 `load_config()` 失败，不默默夹紧。

评测：先只扫 `channels` 三档，再扫 `recall_k × rerank_k`。不要给 Query 加字段。见 [docs/eval.md](docs/eval.md)。

---

## 观测 hook 怎么挂

详细：[docs/observability.md](docs/observability.md)。默认 `NoOpObserver`，`sample_rate: 0`，但 router **每阶段仍调用** hook。

```python
from rag.retriever import CompositeObserver, set_observer

set_observer(CompositeObserver([my_file_sink, my_prom_sink]))
# 或 retrieve(query, observer=my_file_sink)
```

自定义 observer：实现 `on_channel_result` / `on_fusion` / `on_rerank` / `on_retrieve_end` / `on_tier_a_error` 里你需要的那些。超参放在 observer 自己的构造函数里。

A 层查询失败或行校验失败另外落盘到 `artifacts/logs/retriever/`（不受采样率控制）。

---

## 脚本边界（缩略）

| 文件 | 一句话 |
| --- | --- |
| `tier_a.py` | 全仓库唯一 SQL |
| `tier_b.py` | 两路召回 + RRF + 阈值 + 调重排 |
| `rerank.py` | `chunk 列表 → 分数`，对 retriever 透明 |
| `router.py` | 编排；A 失败则降级 |
| `config.py` | 只读 YAML |
| `observe.py` / `error_log.py` | hook / A 层 JSONL |
| `cache.py` | key = 库指纹 + 配置指纹 + 查询 |

完整表：[ARCHITECTURE.md](ARCHITECTURE.md) · [docs/README.md](docs/README.md)。
