# 离线评测节奏

目录 [`rag/eval/`](../../eval/README.md) 只做召回质量，不是 pytest。脚本应读 `artifacts/rules.db` 和 `artifacts/corpora/<strategy_id>/`，不要读 `rag/test/`。

本轮 `gen_eval_set.py` / `run_ablation.py` 只有 docstring，不跑实验。

---

## 1. 两套「hybrid」不要混

| 旋钮 | 含义 | 本文件阶段 |
| --- | --- | --- |
| `RetrievalQuery.retrieval_mode` | 开不开 A / 开不开 B（`exact_only` / `semantic_only` / `hybrid`） | 需要时另做「只有字典 vs 只有散文 vs 两层」；**不是** docs/rag.md 那张三列对比表 |
| YAML `tier_b.channels` | B 层内部：`bm25` / `vector` / `hybrid` | **阶段 A 要扫的**。对应「纯关键词 / 纯向量 / 混合」Recall@5 |

禁止再用 `retrieval_mode=exact_only` 去冒充「纯关键词」。A 层是 SQLite 精确查表，不是 BM25。

---

## 2. 阶段 A：先锁默认 k，只扫三通道

锁死 [`retriever.yaml`](../retriever.yaml) 当前默认：

- A `top_k=8`，BM25 `k=3`，向量 `k=10`
- `recall_k=10`，`rerank_k=3`
- 等权 `1.0` / `1.0`，`rrf_k=60`
- `reranker=identity`（生产默认。真重排名 `minilm_l6` 已注册，评测对比用 `RetrieverConfig` 副本，不要改生产 YAML）
- `score_threshold=null`

只变 `tier_b.channels ∈ {bm25, vector, hybrid}`。

指标：Recall@5（以及 [docs/rag.md](../../../docs/rag.md) 已要求的分类拆分、版本错配比例）。同一份评测用例、三次检索。

据此决定生产默认通道。**不要**在这一阶段扫 k。

`run_ablation.py` 应提供类似入口（docstring 已写）：`--phase a` 只扫 channels。

---

## 3. 阶段 B：通道选定后再扫 k

固定阶段 A 选出的 `channels`（以及仍不扫的权重 / `rrf_k` / 真重排模型）。矩阵：

```text
recall_k ∈ {5, 10, 20}
rerank_k ∈ {1, 3, 5}
```

共 9 格。每格跑同一 eval 集，出表。实现时网格可改，但**必须是配置驱动**，不要写死在 `tier_b.py`。

覆盖方式：`RetrieverConfig` 拷贝或 YAML 副本，见 [config.md](config.md)。不要给 `RetrievalQuery` 加 `recall_k` 字段。

---

## 4. 评测脚本边界

| 文件 | 负责 |
| --- | --- |
| `gen_eval_set.py` | 从 `rules.db` 机械生成 E1/E2/E3（反向映射 / 文档回指 / 退化仓库线索） |
| `hard_cases.yaml` | E4 手标难例 |
| `run_ablation.py` | 阶段 A/B 调度、写 markdown 表 |

评测脚本可以 `import rag.retriever`，可以传入 config 与 observer（例如把每次分数落到 eval 自己的 jsonl）。禁止改 SQL 模板、禁止改 Lance 表、禁止在 eval 里复制一份 RRF。

---

## 5. 和线上观测的衔接

离线表决定默认 YAML。线上用 [observability.md](observability.md) 的 hook 看分数分布是否漂。两边 join 靠 `chunk.id` / `rule.id`，不靠改 Agent 契约。
