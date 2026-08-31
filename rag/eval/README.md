# eval：A/B 层检索评测数据集

本目录包含 A/B 层离线评测集，以及跑分脚本 `run_eval.py`。

## 目录结构

```
eval/
├── build_eval_set.py          # 数据集生成（会冲掉人工对齐的 query，勿随便跑）
├── run_eval.py                # 本轮 A/B 离线评测入口
├── run_ablation.py            # 旧 stub，本轮用 run_eval.py
├── gen_eval_set.py            # 旧 stub
├── hard_cases.yaml            # 人工难例（待填充）
├── test_tier_a/
├── test_tier_b/
├── reports/                   # 跑分产出（每次清空重写）
│   ├── eval_report.md
│   ├── eval_report.html       # 可视化
│   ├── eval_details.jsonl
│   └── eval_context.md
└── docs/
```

## 快速生成数据集

```bash
cd rag
# A/B 层 queries 都已人工正向对齐，再跑会冲掉。
# uv run python eval/build_eval_set.py
```

`eval/test_tier_a/` 与 `eval/test_tier_b/` **都不要用该脚本覆盖**。A 层 20 报错 + 10 语义，`symbols` 只有旧名；B 层 15 报错 + 15 语义。说明见 [`docs/generation_notes.md`](docs/generation_notes.md)。

## 数据集规格

A 层 30 条 groundtruth：10 条 `single` + 20 条 `composite`（2~5 条规则）；query 20 条合成 `error_text` + 10 条 `query_text`。

B 层 30 条 groundtruth：约 22 条 `single` + 8 条 `composite`（剔除离群后）；query 一半是合成 `error_text`，一半是针对正文的 `query_text`。

A 层 groundtruth 是 `MigrationRule` 列表，B 层 groundtruth 是 `ProseChunk` 列表。

查询是自然语言输入，可直接构造为 `RetrievalQuery`：

- A 层查询固定 `retrieval_mode: exact_only`
- B 层查询固定 `retrieval_mode: semantic_only`

详细 schema 见 [`docs/eval_dataset_schema.md`](docs/eval_dataset_schema.md)。

## 跑分

```bash
cd rag
uv run python eval/run_eval.py
```

- 粗召回锁定 `bm25.k=vector.k=20`，权重 0.3:0.7。
- 重排对照已跑：`minilm_l6` 在 Prec_GT / MRR 上全面低于 `identity`。生产保持 identity。
- Prec_GT@K = |GT ∩ top-K| / |GT|；MRR 在前 K 条上算。

会话状态见 [`reports/SESSION_STATE.md`](reports/SESSION_STATE.md)。

产出见 [`reports/eval_report.md`](reports/eval_report.md) 与 [`reports/eval_report.html`](reports/eval_report.html)。

## 生成策略说明

见 [`docs/generation_notes.md`](docs/generation_notes.md)。
