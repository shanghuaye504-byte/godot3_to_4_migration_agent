"""A 层 SQL：detection_method 死门、版本整数比较、空符号、脏行 skip。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from rag.retriever.error_log import schema_drift_total
from rag.retriever.schemas import SymbolKind
from rag.retriever.tier_a import EXPECTED_SCHEMA_VERSION, assert_schema_version, query_rules

_DDL = """
CREATE TABLE migration_rules (
  id TEXT PRIMARY KEY,
  old_symbol TEXT,
  new_symbol TEXT,
  owner TEXT,
  symbol_kind TEXT NOT NULL,
  change TEXT NOT NULL,
  rule_kind TEXT,
  match_tokens TEXT NOT NULL DEFAULT '[]',
  trigger TEXT,
  since_version TEXT,
  since_version_code INTEGER NOT NULL DEFAULT 0,
  until_version TEXT,
  until_version_code INTEGER,
  detection_method TEXT NOT NULL DEFAULT 'agent_retrieval',
  semantic_risk INTEGER NOT NULL DEFAULT 0,
  converter_gap INTEGER NOT NULL DEFAULT 0,
  verifier_blind INTEGER NOT NULL DEFAULT 0,
  agent_action TEXT,
  system_action TEXT,
  warning TEXT,
  snippet TEXT,
  source TEXT NOT NULL,
  source_url TEXT,
  confidence TEXT,
  payload TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?)",
        ("schema_version", EXPECTED_SCHEMA_VERSION),
    )
    return conn


def _insert(conn: sqlite3.Connection, **kwargs: object) -> None:
    cols = {
        "id": "r1",
        "old_symbol": None,
        "new_symbol": None,
        "owner": None,
        "symbol_kind": "method",
        "change": "rename",
        "rule_kind": None,
        "match_tokens": "[]",
        "trigger": None,
        "since_version": "4.0",
        "since_version_code": 40000,
        "until_version": None,
        "until_version_code": None,
        "detection_method": "agent_retrieval",
        "semantic_risk": 0,
        "converter_gap": 0,
        "verifier_blind": 0,
        "agent_action": "apply_rename",
        "system_action": None,
        "warning": None,
        "snippet": None,
        "source": "official_renames",
        "source_url": None,
        "confidence": None,
        "payload": "{}",
    }
    cols.update(kwargs)
    keys = ",".join(cols)
    ph = ",".join("?" * len(cols))
    conn.execute(f"INSERT INTO migration_rules ({keys}) VALUES ({ph})", list(cols.values()))


def test_empty_symbols_returns_empty() -> None:
    conn = _conn()
    _insert(conn, id="r-instance", old_symbol="instance", new_symbol="instantiate")
    assert query_rules(conn, symbols=[], target_version_code=40701) == []


def test_detection_method_hides_traps() -> None:
    conn = _conn()
    _insert(
        conn,
        id="r-visible",
        old_symbol="instance",
        new_symbol="instantiate",
        detection_method="agent_retrieval",
        source="official_renames_skipped",
    )
    _insert(
        conn,
        id="TRAP-001",
        old_symbol="RectangleShape2D",
        owner="RectangleShape2D",
        symbol_kind="trap",
        change="trap",
        detection_method="static_scan_post_l0",
        source="manual_trap",
        agent_action=None,
    )
    hits = query_rules(conn, symbols=["instance", "RectangleShape2D"], target_version_code=40701)
    ids = [r.id for r in hits]
    assert "r-visible" in ids
    assert "TRAP-001" not in ids


def test_version_filter_integer() -> None:
    conn = _conn()
    _insert(conn, id="r-40", old_symbol="yield", since_version="4.0", since_version_code=40000)
    _insert(conn, id="r-48", old_symbol="yield", since_version="4.8", since_version_code=40800)
    hits = query_rules(conn, symbols=["yield"], target_version_code=40701)
    assert [r.id for r in hits] == ["r-40"]


def test_match_tokens_json_each() -> None:
    conn = _conn()
    _insert(
        conn,
        id="r-token",
        old_symbol=None,
        new_symbol="await",
        match_tokens='["yield", "coroutine"]',
        source="manual_rewrite",
        change="rewrite",
        symbol_kind="rewrite",
        agent_action="apply_and_warn",
    )
    hits = query_rules(conn, symbols=["yield"], target_version_code=40701)
    assert len(hits) == 1
    assert hits[0].id == "r-token"
    assert hits[0].match_tokens == ["yield", "coroutine"]


def test_kinds_filter() -> None:
    conn = _conn()
    _insert(conn, id="m", old_symbol="foo", symbol_kind="method")
    _insert(conn, id="c", old_symbol="foo", symbol_kind="class", change="rename")
    hits = query_rules(
        conn,
        symbols=["foo"],
        target_version_code=40701,
        kinds=[SymbolKind.method],
    )
    assert [r.id for r in hits] == ["m"]


def test_source_priority_order() -> None:
    conn = _conn()
    _insert(
        conn,
        id="rewrite",
        old_symbol="instance",
        source="manual_rewrite",
        symbol_kind="rewrite",
        change="rewrite",
    )
    _insert(
        conn,
        id="skipped",
        old_symbol="instance",
        source="official_renames_skipped",
    )
    hits = query_rules(conn, symbols=["instance"], target_version_code=40701)
    assert [r.id for r in hits] == ["skipped", "rewrite"]


def test_dirty_row_skipped(tmp_path: Path) -> None:
    conn = _conn()
    _insert(conn, id="good", old_symbol="instance", new_symbol="instantiate")
    _insert(conn, id="bad", old_symbol="instance", symbol_kind="not_a_real_kind")
    hits = query_rules(
        conn,
        symbols=["instance"],
        target_version_code=40701,
        log_dir=str(tmp_path),
    )
    assert [r.id for r in hits] == ["good"]
    assert schema_drift_total() >= 1
    log = tmp_path / "tier_a.jsonl"
    assert log.is_file()
    assert "row_validation_failed" in log.read_text(encoding="utf-8")


def test_schema_version_mismatch_raises(tmp_path: Path) -> None:
    conn = _conn()
    conn.execute("UPDATE meta SET value = ? WHERE key = ?", ("1", "schema_version"))
    try:
        assert_schema_version(conn, log_dir=str(tmp_path))
        raise AssertionError("should have raised")
    except RuntimeError as exc:
        assert "schema_version" in str(exc)
    assert "schema_version_mismatch" in (tmp_path / "tier_a.jsonl").read_text(encoding="utf-8")
