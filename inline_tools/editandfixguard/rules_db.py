"""迁移规则库的只读访问。

行为依据 NEXT_STEP.md「复用」与「不许自行解释的约定」：规则库只读；
表名用库里实际存在的 `migration_rules` 或 `rules`，列用 `id` 与
`old_symbol`。本包的 G5.1 查询不限 `symbol_kind='class'`。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def _connect(rules_db_path: Path) -> sqlite3.Connection:
    """只读打开规则库。打不开时抛 sqlite3.Error，由调用方映射错误码。"""
    return sqlite3.connect(f"file:{rules_db_path}?mode=ro", uri=True)


def _table_name(conn: sqlite3.Connection) -> str | None:
    """返回库里实际存在的规则表名；两个都没有时返回 None。"""
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "migration_rules" in tables:
        return "migration_rules"
    if "rules" in tables:
        return "rules"
    return None


def load_old_symbols(rules_db_path: Path) -> set[str]:
    """读出规则表全部 `old_symbol`（不限 symbol_kind）。

    库文件不存在、打不开、没有规则表都抛 sqlite3.Error。
    """
    if not Path(rules_db_path).is_file():
        raise sqlite3.Error(f"rules db not found: {rules_db_path}")
    conn = _connect(Path(rules_db_path))
    try:
        table = _table_name(conn)
        if table is None:
            raise sqlite3.Error(f"no rules table in {rules_db_path}")
        rows = conn.execute(f"SELECT old_symbol FROM {table}").fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def rule_exists(rules_db_path: Path, rule_id: object) -> bool:
    """`rule_id` 是否作为 `id` 出现在规则表里。库打不开返回 False。"""
    if rule_id is None or not Path(rules_db_path).is_file():
        return False
    try:
        conn = _connect(Path(rules_db_path))
    except sqlite3.Error:
        return False
    try:
        table = _table_name(conn)
        if table is None:
            return False
        row = conn.execute(
            f"SELECT 1 FROM {table} WHERE id = ? LIMIT 1", (rule_id,)
        ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False
    finally:
        conn.close()
