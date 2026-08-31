# retriever 协议文档索引

短文入口：[../README.md](../README.md)。架构：[../ARCHITECTURE.md](../ARCHITECTURE.md)。配置文件：[../retriever.yaml](../retriever.yaml)。

数据库一行长什么样，仍以 [rag/build/README.md](../../build/README.md) 为准。B 层切块与 Lance 表列，仍以 [CHUNKING.md](../../vault/tier_b_prose/CHUNKING.md) 为准。这里只写**已经建好的两份库，运行时怎么被查出来**。

## 建议阅读顺序

1. [tutorial.md](tutorial.md) — 图像、常识、一条真实报错走完全程。
2. [contracts.md](contracts.md) — `RetrievalQuery` / `RetrievalResult` / 枚举（Agent 契约，冻结）。
3. [config.md](config.md) — 怎么改 YAML、优先级、和 `top_k` 的关系。
4. [tier-a.md](tier-a.md) / [tier-b.md](tier-b.md) — SQL 填空；B 层两路召回、RRF 归一化、重排。
5. [router-runtime.md](router-runtime.md) — 两层订在一起、版本、校验、缓存、工具包装。
6. [observability.md](observability.md) — 怎么挂 hook。
7. [eval.md](eval.md) — 先三通道、再扫 k。
8. [faq.md](faq.md)

实现代码可以仍是 docstring stub。写实现时按这些文档落地，不能改查询结构、不能改已落库字段、不能改「两层一起查」。

## 脚本与功能边界

这张表与 [ARCHITECTURE.md](../ARCHITECTURE.md) 模块地图、每个 `.py` 模块 docstring 的「本文件负责 / 禁止」对齐。不要在错误文件里加逻辑。

### retriever 包（运行时，进 wheel）

| 文件 | 负责 | 禁止 |
| --- | --- | --- |
| [`__init__.py`](../__init__.py) | 对外入口：re-export `retrieve` / `retrieve_cached` | 写 SQL、开库、读 YAML 逻辑 |
| [`schemas.py`](../schemas.py) | 已有枚举 + `MigrationRule` + `ProseChunk` | IO、SQL、检索；本轮不新增模型类 |
| [`config.py`](../config.py) | `load_config()` / `RetrieverConfig` / `config_hash()`，只读同目录 YAML | 查 SQLite / Lance、算 RRF |
| [`tier_a.py`](../tier_a.py) | **全仓库唯一允许拼 SQL** 的 `query_rules()` | import Lance、调 B 层、重排 |
| [`tier_b.py`](../tier_b.py) | `query_prose()`：两路召回 + 加权 RRF + 归一化 + 阈值 + 调用 `RerankFn` | 拼 SQL、决定 `coverage` / `escalate_suggested` |
| [`rerank.py`](../rerank.py) | `RerankFn` 协议 + `identity` / `minilm_l6` | 碰 Lance / SQLite；超参必须闭包在 callable 内 |
| [`router.py`](../router.py) | `retrieve()`：抠符号、调 A、调 B、订结果、调 observer；A 整次失败则空列表并继续 B | 自己写 SQL、自己算 RRF |
| [`cache.py`](../cache.py) | `cache_key(query, manifest_hash, config_hash)` + `retrieve_cached()` | 改命中结果除 `cache_hit=True` 外的字段 |
| [`observe.py`](../observe.py) | `RetrievalObserver` / `NoOpObserver` / `CompositeObserver` 与事件签名 | 检索、默认写远端 |
| [`error_log.py`](../error_log.py) | A 层失败 JSONL 落盘 | 被 B 层 / 重排调用。不叫 `logging.py` |
| [`retriever.yaml`](../retriever.yaml) | 唯一调参文件 | 不是 Python |

调用方向只允许：

```text
Agent 工具
  → __init__.retrieve_cached
    → cache.retrieve_cached
      → router.retrieve
        → config（只读，进程内已 load）
        → tier_a.query_rules → error_log
        → tier_b.query_prose → rerank callable
        → observe.*（每阶段，即使 NoOp）
```

禁止反向 import：`tier_a` 不得 import `router`；`observe` 不得 import `tier_b`。retriever **禁止** `import rag.build`。

### eval 包（离线，不进 wheel）

| 文件 | 负责 | 禁止 |
| --- | --- | --- |
| [`gen_eval_set.py`](../../eval/gen_eval_set.py) | 从 `rules.db` 机械生成 E1/E2/E3 | 改 retriever 内部；读 `test/` |
| [`run_ablation.py`](../../eval/run_ablation.py) | 两阶段消融：先 `channels`，后 `recall_k × rerank_k` | 给 `RetrievalQuery` 加字段 |
| [`hard_cases.yaml`](../../eval/hard_cases.yaml) | E4 难例，人工 | — |

`eval/` 里现有的 `test_*.py` / `conftest.py` 是历史错位文件，不在本目录边界内。

### 不属于 retriever

`rag/build/*`（含 `chunk_prose.py` / `embed_prose.py`）、`workspace_index/*`：检索侧只读成品 `artifacts/`，不 import 它们。
