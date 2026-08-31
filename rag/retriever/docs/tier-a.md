# A 层：从 `RetrievalQuery` 到 SQL，以及失败落盘

请把「拼接」理解成**填空**，不要理解成**组词造句**。

对应脚本：[`tier_a.py`](../tier_a.py)（唯一允许拼 SQL）、[`error_log.py`](../error_log.py)（JSONL）。router 在整次失败时接住异常，见 [router-runtime.md](router-runtime.md)。

---

## 1. 谁有资格碰 SQL

整个仓库里，**只有** `rag/retriever/tier_a.py` 的 `query_rules()` 允许构造并执行 SQL。

```python
def query_rules(
    conn,                              # 已经打开的 rules.db（进程内复用）
    *,
    symbols,                           # 已抠好的符号，来自 router
    target_version_code: int,
    kinds=None,
    limit: int = 8,                    # 来自 YAML tier_a.top_k，或 query.top_k_a
    request_id: str | None = None,     # 只为落盘，不进 SQL
) -> list:                             # list[MigrationRule]
    """唯一允许拼 SQL 的地方。WHERE 结构写死，可变部分只有参数值。"""
```

入参已经**不是**整个 `RetrievalQuery`。`error_text`、`query_text`、`retrieval_mode`、YAML 权重都不会进入 SQL。

---

## 2. 所谓「拼接」只有两种合法动作

| 合法动作 | 例子 | 为什么安全 |
| --- | --- | --- |
| 按 `symbols` 的**个数**重复写 `?` | 1 个符号 → `IN (?)`；3 个 → `IN (?, ?, ?)` | 变的是问号个数，不是列名 |
| `kinds` 非空时追加写死的 `AND symbol_kind IN (?,?,...)` | 值必须先通过 `SymbolKind` | 追加的是固定短语 |

**非法：** f-string 嵌符号；根据 `error_text` 决定要不要 `detection_method` 过滤；调用方传入 WHERE 字符串；`file_hint` 拼成 `LIKE`。

`symbols` 为空：不要去掉 WHERE 把整张表选出来。应返回空列表（抠不出符号 = A 层 0 行，B 层仍可用原文）。

---

## 3. 模板（任何调用者都改不了）

```sql
SELECT *
FROM migration_rules
WHERE detection_method IN ('agent_retrieval', 'agent_retrieval_or_escalate')
  AND since_version_code <= ?
  AND (
        old_symbol IN (/* 每个 symbol 一个 ? */)
     OR new_symbol IN (/* 同上 */)
     OR owner       IN (/* 同上 */)
     OR EXISTS (
          SELECT 1
          FROM json_each(match_tokens)
          WHERE value IN (/* 同上 */)
        )
  )
  -- kinds 非空时：
  -- AND symbol_kind IN (/* 每个 kind 一个 ? */)
ORDER BY since_version_code DESC, source_priority ASC
LIMIT ?;
```

`detection_method IN (...)` 里两个字符串是**常量**，不是 `?`。不要开放给 `RetrievalQuery`。

---

## 4. 把模板逐句翻译成人话

**`SELECT *`**  
后面要用整行构造 `MigrationRule`。不要瘦身成只选 `old_symbol`。

**`FROM migration_rules`**  
一张表，一条 SELECT。见 [build/README.md 第 3 节](../../build/README.md)。

**`WHERE detection_method IN ('agent_retrieval', 'agent_retrieval_or_escalate')`**  
只留 Agent 有权看见的行。同表还有扫描器/过滤器行，不是为了让 Agent 把扫描指令检索出来。

**`AND since_version_code <= ?`**  
整数比较。禁止 `since_version <= '4.7.1'`（`"4.10" < "4.9"` 会错）。`40701` 时：4.0、4.5 留下，4.8 丢掉。

**四个挂钩 OR**

| 列 | 什么时候对得上 |
| --- | --- |
| `old_symbol` | 报错里还是旧名字 |
| `new_symbol` | 拿新名字反查 |
| `owner` | 类型名对上 |
| `match_tokens` | `json_each` 精确相等，不用 `LIKE` |

四个挂钩用**同一组** `symbols`。

**`EXISTS (SELECT 1 FROM json_each(match_tokens) WHERE value IN (...))`**  
`match_tokens` 是 JSON 文本数组。`json_each` 拆成临时表按元素精确匹配。`SELECT 1` 没有业务含义。

**`ORDER BY since_version_code DESC, source_priority ASC`**  
`source_priority` **不是表上的一列**，用 `CASE source WHEN ...` 写死：

```text
official_renames              → 0
official_renames_skipped      → 1
api_diff                      → 2
official_prose                → 3
official_prose_3to4_shader    → 3
manual_trap                   → 4
manual_rewrite                → 4
```

数字越小越靠前。必须确定性排序。

**`LIMIT ?`**  
填 YAML `tier_a.top_k` 或 `query.top_k_a`。数据库层截断。

`kinds` 非空时追加 `AND symbol_kind IN (?)`，拼接前再确认每项都是 `SymbolKind` 成员。

---

## 5. 读出来立刻变成 `MigrationRule`

```python
for row in cursor:
    try:
        rule = MigrationRule.model_validate(row_dict)
    except ValidationError:
        # 落盘 + 计数 + 通知 observer，然后 continue
        continue
    rules.append(rule)
```

单行脏数据不该让整次检索失败。整库协议错了（启动时 `schema_version`）要响亮失败。对照 [docs/hash_and_manifest.md](../../../docs/hash_and_manifest.md)。

---

## 6. 失败怎么接住、日志落到哪

目录默认 `rag/artifacts/logs/retriever/`（gitignore，YAML `observability.log_dir`）。JSONL 追加。同时打 Python `logging`，计数器 `rules_schema_drift_total` 保留。

| 场景 | 谁接住 | 检索还能否继续 | 落盘 `event` |
| --- | --- | --- | --- |
| 启动 `meta.schema_version` ≠ 代码期望 `"2"` | 开库处 | **否**：先写 JSONL，再 `raise RuntimeError` | `schema_version_mismatch` |
| 整次 `query_rules` 抛错（SQLite 损坏等） | **router** | A 当 `[]`，B 照常。禁止把工具调用打成失败 | `query_failed` |
| 单行 `ValidationError` | `query_rules` 循环 | skip 该行 | `row_validation_failed` |

JSONL 每行至少：

```text
ts, level, event, request_id, symbols, target_version_code,
rule_id（若有）, error_type, error_message, row_excerpt
```

`error_log.py` 是唯一允许写这些文件的模块。不要在 `tier_b` / `rerank` 里打开同一路径。observer 的 `on_tier_a_error` / `on_schema_skip` 与 JSONL **同一事件**再转发一份，见 [observability.md](observability.md)。`sample_rate` **不影响**这些事故日志。
