"""connect_rw / connect_ro：建表、WAL、只读拒绝写入。不依赖 parser / daemon。"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlite3

from codeindex.db import connection


def test_rw_creates_four_tables_and_wal(tmp_path: Path) -> None:
    db = tmp_path / ".codeindex" / "index.db"
    conn = connection.connect_rw(db)
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"files", "symbols", "edges", "classes"} <= names

        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"

        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1

        conn.execute(
            "INSERT INTO files (path, content_hash, language, indexed_at) "
            "VALUES ('player.gd', 'h', 'gdscript', 1)"
        )
        conn.commit()
        # WAL 文件在连接打开期间通常会出现；close 时若 checkpoint 干净会被收掉，
        # 所以不在 close 之后断言文件还在。模式已经用 PRAGMA journal_mode 验过。
    finally:
        conn.close()

    assert db.is_file()


def test_ro_can_select_but_cannot_insert(tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    rw = connection.connect_rw(db)
    rw.execute(
        "INSERT INTO files (path, content_hash, language, indexed_at) "
        "VALUES ('a.gd', 'h', 'gdscript', 1)"
    )
    rw.commit()
    rw.close()

    ro = connection.connect_ro(db)
    try:
        n = ro.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert n == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            ro.execute(
                "INSERT INTO files (path, content_hash, language, indexed_at) "
                "VALUES ('b.gd', 'h', 'gdscript', 1)"
            )
    finally:
        ro.close()


def test_reopen_rw_and_ro(tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    first = connection.connect_rw(db)
    first.close()
    second = connection.connect_rw(db)
    try:
        n = second.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert n == 0
    finally:
        second.close()
    ro = connection.connect_ro(db)
    try:
        ro.execute("SELECT COUNT(*) FROM symbols").fetchone()
    finally:
        ro.close()
