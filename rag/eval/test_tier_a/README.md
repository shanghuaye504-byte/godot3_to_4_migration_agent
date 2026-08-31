# A 层检索评测集

本目录包含 A 层（结构化规则字典）检索评测的 groundtruth 与查询集合。

## 文件

| 文件 | 说明 |
| --- | --- |
| `groundtruth.jsonl` | 30 条 groundtruth，每条包含 1~5 个 `MigrationRule` |
| `queries.jsonl` | 30 条自然语言查询，与 groundtruth 一一对应 |

## 样本构成

- `single`：10 条，每条 1 个规则
- `composite`：20 条，每条 2~5 个规则（按 `symbol_kind` 抽的骨架未改）
- **20 条合成报错**（`error_text`）：仿 `check-only` 日志；`symbols` 只有报错里的**旧符号**
- **10 条语义提问**（`query_text`）：问规则实际在记的变更，不是「函数不存在」套模板

query 已按 A 层 SQL 挂钩（`old_symbol` / `new_symbol` / `owner` / `match_tokens`）正向对齐，**不**把 `new_symbol` 塞进 `symbols`。详见 [generation_notes.md](../docs/generation_notes.md)「A 层正向改写」。

## 查询格式

A 层查询固定 `retrieval_mode: exact_only`。报错例：

```json
{
  "gt_id": "a_0002",
  "query": {
    "error_text": "SCRIPT ERROR: Invalid call. Nonexistent function 'find_scancode_from_string' in base 'OS'.",
    "query_text": "",
    "symbols": ["find_scancode_from_string"],
    "target_version": "4.7.1",
    "retrieval_mode": "exact_only"
  }
}
```

语义例：`a_0000` 问 `accessibility_create_sub_text_edit_elements` 是否多了 `is_last_line`，`symbols` 仍只有旧名。

## 不要用 build_eval_set.py 覆盖本目录

```bash
# 会把 new_symbol 写回 symbols，并再次用「函数不存在」套同名签名变更。
# uv run python eval/build_eval_set.py
```

改 query 请直接编辑 `queries.jsonl`，对照 `groundtruth.jsonl` 的 `old_symbol` / `change`。

## 如何跑分

```bash
cd rag
uv run python eval/run_eval.py
```

A 层在脚本里设 `tier_a.top_k=15`，同一结果切片算 Recall @5 / @8 / @15。

## 指标

- **Recall@K** = |GT ∩ top-K| / |GT|，再对 30 条宏平均。
- **Precision@K** = |GT ∩ top-K| / K。
