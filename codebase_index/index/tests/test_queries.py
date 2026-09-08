"""第 4 步 writer 落库 + 第 5 步 queries 只读 SQL。

writer 测例仍走真实 parser（player.gd）。
queries 测例 **禁止** 调 writer / parser：手工 INSERT 固定行，只验证 SQL。
"""

from pathlib import Path

import sqlite3

from codeindex.db import connection, queries, writer

FIXTURES = Path(__file__).parent / "fixtures"
_SCHEMA_SQL = (
    Path(__file__).resolve().parents[1] / "src" / "codeindex" / "db" / "schema.sql"
).read_text(encoding="utf-8")


def test_writer_indexes_player_gd(tmp_path: Path) -> None:
    src = tmp_path / "player.gd"
    src.write_text((FIXTURES / "player.gd").read_text(encoding="utf-8"), encoding="utf-8")
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    try:
        stats = writer.reindex_batch(conn, [src], tmp_path, synced_by="sync_cmd")
        assert stats == {"reindexed": 1, "skipped": 0, "failed": 0}

        names = {row[0] for row in conn.execute("SELECT name FROM symbols")}
        assert {"Player", "take_damage", "_die"} <= names

        edges = {(row[0], row[1]) for row in conn.execute("SELECT from_symbol, to_name FROM edges")}
        assert ("take_damage", "_die") in edges

        row = conn.execute("SELECT name, base_name FROM classes").fetchone()
        assert row == ("Player", "CharacterBody2D")

        synced = conn.execute("SELECT last_synced_by FROM files").fetchone()[0]
        assert synced == "sync_cmd"
    finally:
        conn.close()


def test_writer_idempotent_on_unchanged_hash(tmp_path: Path) -> None:
    src = tmp_path / "player.gd"
    src.write_text((FIXTURES / "player.gd").read_text(encoding="utf-8"), encoding="utf-8")
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    try:
        first = writer.reindex_batch(conn, [src], tmp_path, synced_by="sync_cmd")
        assert first["reindexed"] == 1
        second = writer.reindex_batch(conn, [src], tmp_path, synced_by="watcher")
        assert second["skipped"] == 1
        n = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert n == 1
    finally:
        conn.close()


def test_writer_parse_failure_keeps_file_row_and_empty_symbols(tmp_path: Path) -> None:
    src = tmp_path / "broken.gd"
    src.write_text("func broken(:\n", encoding="utf-8")
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    try:
        stats = writer.reindex_batch(conn, [src], tmp_path, synced_by="watcher")
        assert stats["failed"] == 1
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0] == 0
    finally:
        conn.close()


def test_writer_skips_unknown_extension(tmp_path: Path) -> None:
    src = tmp_path / "readme.md"
    src.write_text("# hi\n", encoding="utf-8")
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    try:
        stats = writer.reindex_batch(conn, [src], tmp_path, synced_by="watcher")
        assert stats["skipped"] == 1
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    finally:
        conn.close()


def test_writer_content_change_replaces_symbols(tmp_path: Path) -> None:
    src = tmp_path / "player.gd"
    src.write_text((FIXTURES / "player.gd").read_text(encoding="utf-8"), encoding="utf-8")
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    try:
        writer.reindex_batch(conn, [src], tmp_path, synced_by="watcher")
        src.write_text("class_name Renamed\nextends Node\n", encoding="utf-8")
        stats = writer.reindex_batch(conn, [src], tmp_path, synced_by="watcher")
        assert stats["reindexed"] == 1
        names = {row[0] for row in conn.execute("SELECT name FROM symbols")}
        assert "Renamed" in names
        assert "take_damage" not in names
        assert conn.execute("SELECT name FROM classes").fetchone()[0] == "Renamed"
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 1
    finally:
        conn.close()


def test_writer_deletes_missing_file(tmp_path: Path) -> None:
    src = tmp_path / "player.gd"
    src.write_text((FIXTURES / "player.gd").read_text(encoding="utf-8"), encoding="utf-8")
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    try:
        writer.reindex_batch(conn, [src], tmp_path, synced_by="watcher")
        src.unlink()
        stats = writer.reindex_batch(conn, [src], tmp_path, synced_by="watcher")
        assert stats["reindexed"] == 1
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0] == 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 第 5 步：queries。图是手画的，不是 parser 从 fixture 源码里挖出来的。
#
# 调用链（README 规定的语义）：  hurt ──call──► take_damage ──call──► _die
# 继承链：                      Boss ──extends──► Player ──extends──► CharacterBody2D
#                               Enemy ──extends──► CharacterBody2D
# ---------------------------------------------------------------------------


def _memory_conn() -> sqlite3.Connection:
    """空的内存库 + 正式 schema。不经过 writer，也不碰磁盘上的 .gd。"""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA_SQL)
    return conn


def _seed_query_graph(conn: sqlite3.Connection) -> None:
    """插入一张已知的符号/边/继承图，列值全部写死。

    故意和 parser 产出「长得像但不保证相同」：例如这里没有 died.emit，
    hurt() 也不是 player.gd 里的函数。SQL 测的是「给定这些行，查询怎么走」，
    不是「GdscriptParser 会不会抽出 take_damage」。
    """
    conn.executemany(
        "INSERT INTO files (id, path, content_hash, language, last_synced_by, indexed_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, "player.gd", "h1", "gdscript", "watcher", 1000.0),
            (2, "hurt.gd", "h2", "gdscript", "watcher", 2000.0),
            (3, "boss.gd", "h3", "gdscript", "watcher", 1500.0),
            (4, "enemy.gd", "h4", "gdscript", "watcher", 500.0),
            (5, "extra.gd", "h5", "gdscript", "watcher", 100.0),
        ],
    )
    conn.executemany(
        "INSERT INTO symbols (file_id, name, kind, line, end_line, class_name, signature) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "Player", "class", 0, 16, None, "class_name Player"),
            (1, "take_damage", "func", 8, 12, "Player", "func take_damage(amount: int) -> void:"),
            (1, "_die", "func", 14, 16, "Player", "func _die() -> void:"),
            (2, "hurt", "func", 3, 6, None, "func hurt():"),
            (5, "take_damage", "func", 1, 2, None, "func take_damage():"),
            (5, "take", "func", 4, 5, None, "func take():"),
            (3, "Boss", "class", 0, 10, None, "class_name Boss"),
            (4, "Enemy", "class", 0, 8, None, "class_name Enemy"),
        ],
    )
    conn.executemany(
        "INSERT INTO edges (file_id, from_symbol, to_name, line, kind) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "take_damage", "_die", 11, "call"),
            (2, "hurt", "take_damage", 5, "call"),
            (1, "Player", "CharacterBody2D", 1, "extends"),
            (1, "_die", "queue_free", 15, "call"),
        ],
    )
    conn.executemany(
        "INSERT INTO classes (file_id, name, base_name, line) VALUES (?, ?, ?, ?)",
        [
            (1, "Player", "CharacterBody2D", 0),
            (3, "Boss", "Player", 0),
            (4, "Enemy", "CharacterBody2D", 0),
        ],
    )
    conn.commit()


def test_find_symbol_exact_match_joins_files_and_sorts() -> None:
    conn = _memory_conn()
    try:
        _seed_query_graph(conn)
        rows = queries.find_symbol(conn, "take_damage")
        assert [r["path"] for r in rows] == ["extra.gd", "player.gd"]
        assert [r["line"] for r in rows] == [1, 8]
        assert rows[1]["class_name"] == "Player"
        assert rows[1]["kind"] == "func"
        assert queries.find_symbol(conn, "take")[0]["name"] == "take"
        assert queries.find_symbol(conn, "take_damage")[0]["name"] != "take"
        assert queries.find_symbol(conn, "no_such_symbol") == []
    finally:
        conn.close()


def test_status_counts_and_max_indexed_at() -> None:
    conn = _memory_conn()
    try:
        empty = queries.status(conn)
        assert empty == {"files": 0, "symbols": 0, "last_indexed_at": None}

        _seed_query_graph(conn)
        got = queries.status(conn)
        assert got["files"] == 5
        assert got["symbols"] == 8
        assert got["last_indexed_at"] == 2000.0
    finally:
        conn.close()


def test_call_chain_walks_callers_up_to_depth() -> None:
    conn = _memory_conn()
    try:
        _seed_query_graph(conn)

        one = queries.call_chain(conn, "_die", depth=1)
        assert [(r["name"], r["depth"], r["path"], r["line"]) for r in one] == [
            ("take_damage", 1, "player.gd", 11),
        ]
        assert one[0]["to_name"] == "_die"
        assert one[0]["class_name"] == "Player"

        full = queries.call_chain(conn, "_die", depth=3)
        assert [(r["name"], r["depth"]) for r in full] == [
            ("take_damage", 1),
            ("hurt", 2),
        ]
        assert full[1]["path"] == "hurt.gd"
        assert full[1]["to_name"] == "take_damage"

        names = {r["name"] for r in full}
        assert "Player" not in names
        assert "queue_free" not in names

        assert queries.call_chain(conn, "_die", depth=0) == []
        assert queries.call_chain(conn, "nobody_calls_this") == []
    finally:
        conn.close()


def test_class_hierarchy_ancestors_and_subclasses() -> None:
    conn = _memory_conn()
    try:
        _seed_query_graph(conn)

        player = queries.class_hierarchy(conn, "Player")
        assert player["name"] == "Player"
        assert [a["name"] for a in player["ancestors"]] == ["CharacterBody2D"]
        assert player["ancestors"][0]["path"] is None
        assert [s["name"] for s in player["subclasses"]] == ["Boss"]
        assert player["subclasses"][0]["path"] == "boss.gd"

        boss = queries.class_hierarchy(conn, "Boss")
        assert [a["name"] for a in boss["ancestors"]] == ["Player", "CharacterBody2D"]
        assert boss["ancestors"][0]["path"] == "player.gd"
        assert boss["subclasses"] == []

        engine = queries.class_hierarchy(conn, "CharacterBody2D")
        assert engine["ancestors"] == []
        assert [s["name"] for s in engine["subclasses"]] == ["Enemy", "Player"]
        assert [s["path"] for s in engine["subclasses"]] == ["enemy.gd", "player.gd"]
    finally:
        conn.close()

