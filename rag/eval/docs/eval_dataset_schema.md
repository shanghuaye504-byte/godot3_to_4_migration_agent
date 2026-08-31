# 评测集数据格式

本目录说明 `eval/test_tier_a/` 与 `eval/test_tier_b/` 下 JSONL 文件的 schema。

## 文件结构

```
eval/test_tier_a/
├── groundtruth.jsonl   # 30 条 groundtruth
└── queries.jsonl       # 30 条与 groundtruth 一一对应的查询

eval/test_tier_b/
├── groundtruth.jsonl
└── queries.jsonl
```

`groundtruth.jsonl` 与 `queries.jsonl` 通过 `gt_id` 一一对应。

---

## groundtruth.jsonl

每行一个 JSON 对象：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `gt_id` | string | 唯一标识，如 `a_0000`、`b_0015` |
| `type` | string | `single` 或 `composite` |
| `target_version` | string | 目标 Godot 版本，默认 `4.7.1` |
| `items` | list | groundtruth 条目列表 |

### A 层 `items` 元素

元素字段来自 `migration_rules` 表，保留检索评测所需的最小字段：

```json
{
  "id": "official_renames:4.0:_:method:disable_plugin",
  "old_symbol": "disable_plugin",
  "new_symbol": "_disable_plugin",
  "owner": null,
  "symbol_kind": "method",
  "change": "rename",
  "warning": null,
  "snippet": null,
  "source": "official_renames",
  "source_url": null,
  "agent_action": "apply_rename",
  "since_version": "4.0"
}
```

### B 层 `items` 元素

元素字段来自 LanceDB `corpus` 表：

```json
{
  "id": "rst/gdscript_basics.rst::c0014",
  "text": "2D Rectangle type containing two vectors fields...",
  "heading_path": ["GDScript reference", "Built-in types", "Vector built-in types", "Rect2"],
  "related_symbols": ["Rect2", "Vector2", "Vector3"],
  "source": "official_doc",
  "source_file": "gdscript_basics.rst",
  "source_url": "...",
  "since_version": "4.0"
}
```

---

## queries.jsonl

每行一个 JSON 对象：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `gt_id` | string | 对应 groundtruth 的 id |
| `query` | object | 可直接传给 `RetrievalQuery` 的字典 |

### A 层 `query` 示例

```json
{
  "error_text": "Invalid call. Nonexistent function 'disable_plugin' in base 'Node'.",
  "symbols": ["disable_plugin", "_disable_plugin"],
  "target_version": "4.7.1",
  "retrieval_mode": "exact_only"
}
```

A 层查询使用 `exact_only`，只测 A 层字典召回，不触发 B 层 embedding。

### B 层 `query` 示例

```json
{
  "error_text": "",
  "query_text": "What changed with Rect2 in Godot 4?",
  "symbols": ["Rect2", "Vector2", "Vector3"],
  "target_version": "4.7.1",
  "retrieval_mode": "semantic_only"
}
```

B 层查询使用 `semantic_only`，只测 B 层散文召回，不触发 A 层 SQL。

---

## 组合样本

30 条 groundtruth 中：

- 10 条 `single`：`items` 长度为 1
- 20 条 `composite`：`items` 长度为 2~5

A 层组合样本按 `symbol_kind` 分组，保证同组内规则类型一致。  
B 层组合样本按 `source_file` 分组，保证同组内 chunks 来源一致。

组合查询把多个条目合并成一条自然语言输入：A 层拼接报错片段与符号，B 层围绕多个主题生成综合问题。
