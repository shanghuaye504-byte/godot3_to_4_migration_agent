"""A 层精确查表。全仓库唯一允许构造并执行 SQL 的地方。

本文件负责：``query_rules()``。WHERE 骨架写死，可变部分只有 ``?`` 绑定值。

禁止：import Lance、调用 ``tier_b`` / ``rerank`` / ``router``、用 f-string 拼符号、
根据 ``error_text`` 决定是否过滤 ``detection_method``。
调用方：仅 ``router.retrieve``。
被调用方：``error_log``（单行校验失败时）。

对应文档：``rag/retriever/docs/tier-a.md``。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from rag.retriever.error_log import (
    increment_schema_drift,
    write_tier_a_event,
)
from rag.retriever.observe import TierAErrorEvent, safe_observe
from rag.retriever.schemas import MigrationRule, SymbolKind

EXPECTED_SCHEMA_VERSION = "2"

_JSON_FIELDS = ("match_tokens", "trigger", "payload")
_BOOL_FIELDS = ("semantic_risk", "converter_gap", "verifier_blind")


def assert_schema_version(
    conn: sqlite3.Connection,
    *,
    request_id: str | None = None,
    log_dir: str | None = None,
) -> None:
    """启动时断言 ``meta.schema_version`` 等于代码期望的 ``\"2\"``。

    不匹配：先写 JSONL，再 ``raise RuntimeError``，拒绝服务。
    """
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?",
            ("schema_version",),
        ).fetchone()
    except sqlite3.Error as exc:
        write_tier_a_event(
            event="schema_version_mismatch",
            request_id=request_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
            log_dir=log_dir,
        )
        increment_schema_drift()
        raise RuntimeError("无法读取 rules.db 的 meta.schema_version") from exc
    value = row[0] if row is not None else None
    if str(value) != EXPECTED_SCHEMA_VERSION:
        msg = (
            f"rules.db schema_version={value!r}，"
            f"代码期望 {EXPECTED_SCHEMA_VERSION!r}"
        )
        write_tier_a_event(
            event="schema_version_mismatch",
            request_id=request_id,
            error_type="schema_version_mismatch",
            error_message=msg,
            log_dir=log_dir,
        )
        increment_schema_drift()
        raise RuntimeError(msg)


def _placeholders(n: int) -> str:
    return ",".join("?" * n)


def _coerce_row(row: sqlite3.Row) -> dict[str, Any]:
    data = {k: row[k] for k in row.keys()}
    for key in _JSON_FIELDS:
        val = data.get(key)
        if val is None:
            if key == "match_tokens":
                data[key] = []
            elif key == "payload":
                data[key] = {}
            continue
        if isinstance(val, (dict, list)):
            continue
        if isinstance(val, (bytes, bytearray)):
            val = val.decode("utf-8")
        if isinstance(val, str):
            if not val.strip():
                data[key] = [] if key == "match_tokens" else ({} if key == "payload" else None)
                continue
            data[key] = json.loads(val)
    for key in _BOOL_FIELDS:
        data[key] = bool(data.get(key))
    return data


def _excerpt(row: sqlite3.Row, limit: int = 240) -> str:
    try:
        text = json.dumps({k: row[k] for k in row.keys()}, ensure_ascii=False, default=str)
    except Exception:
        text = str(tuple(row))
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def query_rules(
    conn: sqlite3.Connection,
    *,
    symbols: Sequence[str],
    target_version_code: int,
    kinds: Sequence[SymbolKind | str] | None = None,
    limit: int = 8,
    request_id: str | None = None,
    observer: Any = None,
    log_dir: str | None = None,
) -> list[MigrationRule]:
    """按写死模板查询 ``migration_rules``。

    ``symbols`` 为空时返回 ``[]``，禁止去掉 WHERE 把整张表选出来。
    单行 ``ValidationError``：写 JSONL、计数、``on_schema_skip``，然后 skip。
    """
    if not symbols:
        return []

    kind_values: list[str] = []
    if kinds:
        for item in kinds:
            kind = item if isinstance(item, SymbolKind) else SymbolKind(item)
            kind_values.append(kind.value)

    n = len(symbols)
    ph = _placeholders(n)
    sql = f"""
SELECT *
FROM migration_rules
WHERE detection_method IN ('agent_retrieval', 'agent_retrieval_or_escalate')
  AND since_version_code <= ?
  AND (
        old_symbol IN ({ph})
     OR new_symbol IN ({ph})
     OR owner       IN ({ph})
     OR EXISTS (
          SELECT 1
          FROM json_each(COALESCE(match_tokens, '[]'))
          WHERE value IN ({ph})
        )
  )
"""
    params: list[Any] = [target_version_code]
    params.extend(symbols)
    params.extend(symbols)
    params.extend(symbols)
    params.extend(symbols)
    if kind_values:
        sql += f"  AND symbol_kind IN ({_placeholders(len(kind_values))})\n"
        params.extend(kind_values)
    sql += """
ORDER BY since_version_code DESC,
  CASE source
    WHEN 'official_renames' THEN 0
    WHEN 'official_renames_skipped' THEN 1
    WHEN 'api_diff' THEN 2
    WHEN 'official_prose' THEN 3
    WHEN 'official_prose_3to4_shader' THEN 3
    WHEN 'manual_trap' THEN 4
    WHEN 'manual_rewrite' THEN 4
    ELSE 5
  END ASC
LIMIT ?
"""
    params.append(int(limit))

    cursor = conn.execute(sql, params)
    rules: list[MigrationRule] = []
    for row in cursor:
        try:
            payload = _coerce_row(row)
            rule = MigrationRule.model_validate(payload)
        except (ValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
            rule_id = None
            try:
                rule_id = row["id"] if "id" in row.keys() else None
            except Exception:
                rule_id = None
            excerpt = _excerpt(row)
            write_tier_a_event(
                event="row_validation_failed",
                level="warning",
                request_id=request_id,
                symbols=list(symbols),
                target_version_code=target_version_code,
                rule_id=str(rule_id) if rule_id is not None else None,
                error_type=type(exc).__name__,
                error_message=str(exc),
                row_excerpt=excerpt,
                log_dir=log_dir,
            )
            increment_schema_drift()
            safe_observe(
                observer,
                "on_schema_skip",
                TierAErrorEvent(
                    event="row_validation_failed",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    rule_id=str(rule_id) if rule_id is not None else None,
                    row_excerpt=excerpt,
                    symbols=list(symbols),
                    target_version_code=target_version_code,
                    request_id=request_id,
                ),
            )
            continue
        rules.append(rule)
    return rules
