"""Step 3 落库验收。

见 codebase_index/NEXT_STEP.md Step 3 与 scenecheckfixture/README.md。
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from codeindex.db import connection, writer

FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "scenecheckfixture"


def _setup_project(tmp_path: Path, *fixture_names: str) -> tuple[sqlite3.Connection, Path]:
    """建一个临时工程目录，复制指定夹具文件进去，返回 (conn, project_root)。"""
    for name in fixture_names:
        src = FIXTURE_ROOT / name
        dst = tmp_path / src.name
        shutil.copy(src, dst)
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    return conn, tmp_path


def _reindex(conn, root: Path, *filenames: str):
    paths = [root / f for f in filenames]
    return writer.reindex_batch(conn, paths, root, "sync_cmd")


# ---------------------------------------------------------------------------
# res:// 路径解析
# ---------------------------------------------------------------------------


def test_res_path_resolved(tmp_path: Path) -> None:
    conn, root = _setup_project(tmp_path, "godot3/real_dodge_main.tscn")
    try:
        _reindex(conn, root, "real_dodge_main.tscn")
        rows = conn.execute(
            "SELECT ext_id, ref_path, resolved_file FROM scene_ext WHERE path = 'real_dodge_main.tscn' ORDER BY ext_id"
        ).fetchall()
        assert len(rows) == 6
        # res://Main.gd → Main.gd（相对 project_root）
        assert rows[0] == ("1", "res://Main.gd", "Main.gd")
        assert rows[1] == ("2", "res://Mob.tscn", "Mob.tscn")
        # 夹具里没有这些文件，resolved_file 仍是路径（不是 None）
        # 因为 L3 只算路径，不判存在性
    finally:
        conn.close()


def test_relative_path_resolved(tmp_path: Path) -> None:
    """两个 generated 里的 icon.png 应落到该 .tscn 所在目录。"""
    sub = tmp_path / "scenes"
    sub.mkdir()
    shutil.copy(FIXTURE_ROOT / "godot3" / "generated_format_matrix.tscn", sub / "matrix.tscn")
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    try:
        writer.reindex_batch(conn, [sub / "matrix.tscn"], tmp_path, "sync_cmd")
        row = conn.execute(
            "SELECT ref_path, resolved_file FROM scene_ext WHERE path = 'scenes/matrix.tscn' AND ext_id = '1'"
        ).fetchone()
        assert row is not None
        assert row[0] == "icon.png"
        assert row[1] == "scenes/icon.png"
    finally:
        conn.close()


def test_colon_suffix_stripped(tmp_path: Path) -> None:
    """res://a.tres::Resource_x 的 :: 后缀应去掉。"""
    (tmp_path / "test.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n'
        '[ext_resource type="Resource" path="res://data.tres::MyRes" id="1"]\n'
        '[node name="R" type="Node"]\n',
        encoding="utf-8",
    )
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    try:
        writer.reindex_batch(conn, [tmp_path / "test.tscn"], tmp_path, "sync_cmd")
        row = conn.execute(
            "SELECT ref_path, resolved_file FROM scene_ext WHERE ext_id = '1'"
        ).fetchone()
        assert row[0] == "res://data.tres::MyRes"
        assert row[1] == "data.tres"
    finally:
        conn.close()


def test_uid_only_no_path(tmp_path: Path) -> None:
    """只有 uid、没有 path 时 resolved_file 为 NULL。"""
    (tmp_path / "test.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n'
        '[ext_resource type="Script" uid="uid://abc123" id="1"]\n'
        '[node name="R" type="Node"]\n',
        encoding="utf-8",
    )
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    try:
        writer.reindex_batch(conn, [tmp_path / "test.tscn"], tmp_path, "sync_cmd")
        row = conn.execute(
            "SELECT ref_path, resolved_file FROM scene_ext WHERE ext_id = '1'"
        ).fetchone()
        assert row[0] is None
        assert row[1] is None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 坏场景不弄垮整批
# ---------------------------------------------------------------------------


def test_malformed_scene_does_not_rollback_batch(tmp_path: Path) -> None:
    (tmp_path / "good.gd").write_text("class_name Good\nfunc ready():\n\tpass\n", encoding="utf-8")
    (tmp_path / "good.tscn").write_text(
        '[gd_scene format=3]\n[node name="R" type="Node"]\n', encoding="utf-8"
    )
    (tmp_path / "bad.tscn").write_text(
        '[gd_scene format=3]\n[node name="A" type="Node"]\ntext = "unclosed\n', encoding="utf-8"
    )
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    try:
        stats = writer.reindex_batch(
            conn,
            [tmp_path / "good.gd", tmp_path / "good.tscn", tmp_path / "bad.tscn"],
            tmp_path,
            "sync_cmd",
        )
        assert stats["reindexed"] == 3
        assert stats["failed"] == 0
        # .gd 正常进 files
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 1
        # 好场景 OK
        row = conn.execute(
            "SELECT parse_status FROM scene_files WHERE path = 'good.tscn'"
        ).fetchone()
        assert row[0] == "OK"
        # 坏场景 MALFORMED
        row = conn.execute(
            "SELECT parse_status, problem_count FROM scene_files WHERE path = 'bad.tscn'"
        ).fetchone()
        assert row[0] == "MALFORMED"
        assert row[1] > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# .tscn / .tres 不进 files 表
# ---------------------------------------------------------------------------


def test_tscn_not_in_files_table(tmp_path: Path) -> None:
    conn, root = _setup_project(tmp_path, "godot3/real_dodge_main.tscn")
    try:
        _reindex(conn, root, "real_dodge_main.tscn")
        paths = [r[0] for r in conn.execute("SELECT path FROM files")]
        assert "real_dodge_main.tscn" not in paths
        assert conn.execute("SELECT COUNT(*) FROM scene_files").fetchone()[0] == 1
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 增量等于全量
# ---------------------------------------------------------------------------


def test_incremental_equals_full_rebuild(tmp_path: Path) -> None:
    """随机编辑后，增量 sync 的 scene_* 与全量重建逐行一致。"""
    fixture = FIXTURE_ROOT / "godot3" / "real_dodge_main.tscn"

    def _build(root: Path, files: list[Path]) -> dict[str, list[tuple]]:
        db = root / "index.db"
        conn = connection.connect_rw(db)
        try:
            writer.reindex_batch(conn, files, root, "sync_cmd")
            result = {}
            for table in ("scene_files", "scene_nodes", "scene_ext", "scene_sub", "scene_conn", "scene_refs"):
                result[table] = conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
            return result
        finally:
            conn.close()

    # 全量
    full_root = tmp_path / "full"
    full_root.mkdir()
    f1 = full_root / "main.tscn"
    shutil.copy(fixture, f1)
    full = _build(full_root, [f1])

    # 增量：先建，再改，再 sync
    inc_root = tmp_path / "inc"
    inc_root.mkdir()
    f2 = inc_root / "main.tscn"
    shutil.copy(fixture, f2)
    _build(inc_root, [f2])  # 第一次
    # 修改文件（加一个节点）
    content = f2.read_text(encoding="utf-8")
    content += '\n[node name="Extra" type="Node" parent="."]\n'
    f2.write_text(content, encoding="utf-8")
    inc = _build(inc_root, [f2])  # 第二次（增量）

    # 全量重建同样的内容
    f1.write_text(content, encoding="utf-8")
    full2 = _build(full_root, [f1])

    for table in full2:
        assert full2[table] == inc[table], f"{table} 增量与全量不一致"


# ---------------------------------------------------------------------------
# 超限与二进制
# ---------------------------------------------------------------------------


def test_oversize(tmp_path: Path) -> None:
    big = tmp_path / "big.tscn"
    big.write_bytes(b"[gd_scene format=3]\n" + b";" * (4 * 1024 * 1024 + 1))
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    try:
        writer.reindex_batch(conn, [big], tmp_path, "sync_cmd")
        row = conn.execute(
            "SELECT parse_status, problem_count FROM scene_files WHERE path = 'big.tscn'"
        ).fetchone()
        assert row[0] == "SKIPPED_OVERSIZE"
        assert row[1] == 0
    finally:
        conn.close()


def test_binary(tmp_path: Path) -> None:
    binf = tmp_path / "bin.tscn"
    binf.write_bytes(b"[gd_scene format=3]\n\x00\x01\x02")
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    try:
        writer.reindex_batch(conn, [binf], tmp_path, "sync_cmd")
        row = conn.execute(
            "SELECT parse_status, problem_count FROM scene_files WHERE path = 'bin.tscn'"
        ).fetchone()
        assert row[0] == "BINARY"
        assert row[1] == 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 删除场景文件
# ---------------------------------------------------------------------------


def test_delete_scene_removes_rows(tmp_path: Path) -> None:
    conn, root = _setup_project(tmp_path, "godot3/real_dodge_main.tscn")
    try:
        _reindex(conn, root, "real_dodge_main.tscn")
        assert conn.execute("SELECT COUNT(*) FROM scene_files").fetchone()[0] == 1
        # 删除文件
        (root / "real_dodge_main.tscn").unlink()
        _reindex(conn, root, "real_dodge_main.tscn")
        for table in ("scene_files", "scene_nodes", "scene_ext", "scene_sub", "scene_conn", "scene_refs"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, f"{table} 未清空"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# scene_nodes 的 in_unresolved_subtree
# ---------------------------------------------------------------------------


def test_unresolved_subtree_flag(tmp_path: Path) -> None:
    conn, root = _setup_project(tmp_path, "godot3/real_dodge_main.tscn")
    try:
        _reindex(conn, root, "real_dodge_main.tscn")
        rows = conn.execute(
            "SELECT node_path, in_unresolved_subtree FROM scene_nodes WHERE path = 'real_dodge_main.tscn'"
        ).fetchall()
        by_path = dict(rows)
        # Player 和 HUD 是 instance 节点
        assert by_path["Player"] == 1
        assert by_path["HUD"] == 1
        # Main 不是
        assert by_path["Main"] == 0
    finally:
        conn.close()
