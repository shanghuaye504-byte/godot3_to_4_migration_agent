# B 层检索评测集

本目录包含 B 层（散文语料）检索评测的 groundtruth 与查询集合。

## 文件

| 文件 | 说明 |
| --- | --- |
| `groundtruth.jsonl` | 30 条 groundtruth，每条包含 1~5 个 `ProseChunk` |
| `queries.jsonl` | 30 条自然语言查询，与 groundtruth 一一对应 |

## 样本构成

- 30 条 `gt_id` 保留自第一版抽样；组合样本已剔除强不相关离群 chunk，现行约 22 条 `single` + 8 条 `composite`，共 38 个 chunk。
- **15 条合成报错**（`error_text` + 正文符号）：模拟升级后的 Godot 报错 / 失效调用。
- **15 条语义提问**（`query_text`）：按对应 chunk **正文**在讨论的问题来问，不是 heading 套模板。

query 已相对 chunk.text 做过正向对齐。详见 [generation_notes.md](../docs/generation_notes.md)「B 层正向改写」。

## 查询格式

B 层查询使用 `RetrievalQuery` 的子集，并固定 `retrieval_mode: semantic_only`：

```json
{
  "gt_id": "b_0005",
  "query": {
    "error_text": "Invalid call. Nonexistent function 'interpolate_property' in base 'Tween'. ...",
    "query_text": "",
    "symbols": ["Tween", "interpolate_property", "create_tween"],
    "target_version": "4.7.1",
    "retrieval_mode": "semantic_only"
  }
}
```

## 不要用 build_eval_set.py 覆盖本目录

```bash
# 会按 heading 模板重生成，冲掉正向对齐的 query。
# uv run python eval/build_eval_set.py
```

改 query 请直接编辑 `queries.jsonl`，并对照 `groundtruth.jsonl` 里的 `text`。

## 如何跑分

```bash
cd rag
uv run python eval/run_eval.py
```

B 层粗召回已锁定 `bm25.k = vector.k = 20`。本轮扫 RRF 权重，报 Recall@10 与 MRR。

## 指标

- **Recall@K** = |GT ∩ top-K| / |GT|，再对 30 条宏平均。
- **MRR** = 1 / 第一条 GT 命中的排名。
