"""Invariant checks against A-layer compile artifacts.

Requires a prior ``build/build_all.sh`` run. Queries ``artifacts/rules.db``
directly (retriever is out of scope this round).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rag.version_codec import version_to_code

RAG = Path(__file__).resolve().parent.parent
DB = RAG / "artifacts" / "rules.db"
PROSE = RAG / "vault" / "tier_b_prose"
CONTEXT = RAG / "artifacts" / "agent_context" / "upgrading_to_godot_4.rst"
GUIDE = RAG / "vault" / "tier_a_official" / "upgrading_to_godot_4.rst"


@pytest.fixture(scope="module")
def conn() -> sqlite3.Connection:
    if not DB.exists():
        pytest.skip(f"rules.db missing at {DB}; run build/build_all.sh first")
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_schema_version(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    assert row is not None
    assert row[0] == "2"


def test_meta_versions(conn: sqlite3.Connection) -> None:
    meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    assert meta["godot_version"] == "4.7.1"
    assert meta["api_from"] == "4.0.4"
    assert meta["api_to"] == "4.7.1"


def test_trap_004_and_007_not_inserted(conn: sqlite3.Connection) -> None:
    ids = {
        r[0]
        for r in conn.execute(
            "SELECT id FROM migration_rules WHERE id IN ('TRAP-004', 'TRAP-007')"
        )
    }
    assert ids == set()


def test_trap_001_is_static_scan(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT * FROM migration_rules WHERE id = 'TRAP-001'").fetchone()
    assert row is not None
    assert row["detection_method"] == "static_scan_post_l0"
    assert row["old_symbol"] == "RectangleShape2D"
    assert row["source"] == "manual_trap"


def test_area_rename(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT * FROM migration_rules WHERE old_symbol = 'Area' AND new_symbol = 'Area3D'"
    ).fetchone()
    assert row is not None
    assert row["source"] == "official_renames"
    assert row["symbol_kind"] == "class"
    assert row["converter_gap"] == 0


def test_instance_skipped(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT * FROM migration_rules WHERE old_symbol = 'instance' "
        "AND source = 'official_renames_skipped'"
    ).fetchone()
    assert row is not None
    assert row["new_symbol"] == "instantiate"
    assert row["converter_gap"] == 1
    assert row["agent_action"] == "apply_and_warn"


def test_hint_albedo(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT * FROM migration_rules WHERE old_symbol = 'hint_albedo' AND symbol_kind = 'shader'"
    ).fetchone()
    assert row is not None
    assert row["new_symbol"] == "source_color"
    assert row["source"] == "official_renames"


def test_yield_rewrite(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT * FROM migration_rules WHERE id = 'REWRITE-001'").fetchone()
    assert row is not None
    assert row["old_symbol"] == "yield"
    assert row["detection_method"] == "agent_retrieval"
    assert row["source"] == "manual_rewrite"
    assert row["agent_action"] == "apply_and_warn"


def test_get_meta_list_4_1(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT * FROM migration_rules WHERE id = 'official_prose:4.1:Object:method:get_meta_list'"
    ).fetchone()
    assert row is not None
    assert row["since_version"] == "4.1"
    assert row["since_version_code"] == 40100
    assert row["source"] == "official_prose"
    assert row["change"] in {"type", "signature"}


def test_shader_carveout_four_rows(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id FROM migration_rules WHERE source = 'official_prose_3to4_shader' ORDER BY id"
    ).fetchall()
    ids = [r[0] for r in rows]
    assert ids == [
        "SHADER-3TO4-001",
        "SHADER-3TO4-002",
        "SHADER-3TO4-003",
        "SHADER-3TO4-004",
    ]
    reverse = conn.execute(
        "SELECT since_version, since_version_code FROM migration_rules WHERE id = 'SHADER-3TO4-004'"
    ).fetchone()
    assert reverse["since_version"] == "4.3"
    assert reverse["since_version_code"] == 40300


def test_version_filter_4_4_vs_4_7(conn: sqlite3.Connection) -> None:
    n44 = conn.execute(
        "SELECT COUNT(*) FROM migration_rules WHERE since_version_code <= ?",
        (version_to_code("4.4"),),
    ).fetchone()[0]
    n47 = conn.execute(
        "SELECT COUNT(*) FROM migration_rules WHERE since_version_code <= ?",
        (version_to_code("4.7.1"),),
    ).fetchone()[0]
    assert n47 > n44
    only_late = conn.execute(
        "SELECT COUNT(*) FROM migration_rules WHERE since_version_code > ?",
        (version_to_code("4.4"),),
    ).fetchone()[0]
    assert only_late == n47 - n44
    assert only_late > 0


def test_agent_context_is_full_copy() -> None:
    assert CONTEXT.exists()
    assert CONTEXT.read_text(encoding="utf-8") == GUIDE.read_text(encoding="utf-8")


def test_prose_jsonl_present() -> None:
    expected = [
        "upgrading_to_godot_4.1.rst.prose.jsonl",
        "upgrading_to_godot_4.2.rst.prose.jsonl",
        "upgrading_to_godot_4.3.rst.prose.jsonl",
        "upgrading_to_godot_4.4.rst.prose.jsonl",
        "upgrading_to_godot_4.5.rst.prose.jsonl",
        "upgrading_to_godot_4.6.rst.prose.jsonl",
        "upgrading_to_godot_4.7.rst.prose.jsonl",
        "upgrading_to_godot_4.rst.updating_shaders.prose.jsonl",
    ]
    missing = [name for name in expected if not (PROSE / name).exists()]
    if missing:
        pytest.skip(
            f"prose jsonl files missing (build pipeline not run): {missing}"
        )
    for name in expected:
        path = PROSE / name
        text = path.read_text(encoding="utf-8").strip()
        assert text, f"{name} is empty"
        import json

        rec = json.loads(text.splitlines()[0])
        for key in ("heading_path", "text", "since_version", "source_file"):
            assert key in rec, f"{name} missing {key}"


def test_no_csharp_renames(conn: sqlite3.Connection) -> None:
    n = conn.execute(
        "SELECT COUNT(*) FROM migration_rules "
        "WHERE json_extract(payload, '$.cpp_array') LIKE 'csharp_%'"
    ).fetchone()[0]
    assert n == 0
