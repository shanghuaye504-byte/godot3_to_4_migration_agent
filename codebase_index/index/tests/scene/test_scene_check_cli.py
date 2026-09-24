"""Step 5 的 scene-check 命令验收。

见 codebase_index/NEXT_STEP.md Step 5。
"""

from __future__ import annotations

from pathlib import Path

from codeindex.db import connection, writer
from codeindex.scene.baseline import freeze_baseline
from codeindex.scene.check import scene_check


def _setup_two_scripts(tmp_path: Path):
    """两个 .gd 各被一个场景引用。"""
    (tmp_path / "a.gd").write_text("class_name A\nfunc work():\n\tpass\n", encoding="utf-8")
    (tmp_path / "b.gd").write_text("class_name B\nfunc work():\n\tpass\n", encoding="utf-8")
    (tmp_path / "use_a.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n'
        '[ext_resource type="Script" path="res://a.gd" id="1"]\n'
        '[node name="R" type="Node"]\n'
        '[node name="N" type="A" parent="."]\n'
        'script = ExtResource("1")\n',
        encoding="utf-8",
    )
    (tmp_path / "use_b.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n'
        '[ext_resource type="Script" path="res://b.gd" id="1"]\n'
        '[node name="R" type="Node"]\n'
        '[node name="N" type="B" parent="."]\n'
        'script = ExtResource("1")\n',
        encoding="utf-8",
    )
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    writer.reindex_batch(
        conn,
        [tmp_path / "a.gd", tmp_path / "b.gd", tmp_path / "use_a.tscn", tmp_path / "use_b.tscn"],
        tmp_path,
        "sync_cmd",
    )
    freeze_baseline(conn, [])
    return conn, tmp_path


# ---------------------------------------------------------------------------
# --path 闭包
# ---------------------------------------------------------------------------


def test_path_closure_includes_referencing_scene(tmp_path: Path) -> None:
    conn, root = _setup_two_scripts(tmp_path)
    try:
        # 删掉 class_name A
        (root / "a.gd").write_text("func work():\n\tpass\n", encoding="utf-8")
        writer.reindex_batch(conn, [root / "a.gd"], root, "sync_cmd")

        # 传 a.gd：只包含 use_a.tscn 的问题
        r = scene_check(conn, root, paths=["a.gd"])
        assert len(r["regression"]) == 1
        assert r["regression"][0]["path"] == "use_a.tscn"
        assert "class:A" in r["regression"][0]["subject"]
    finally:
        conn.close()


def test_path_closure_excludes_unrelated_scene(tmp_path: Path) -> None:
    conn, root = _setup_two_scripts(tmp_path)
    try:
        # 删掉 class_name A
        (root / "a.gd").write_text("func work():\n\tpass\n", encoding="utf-8")
        writer.reindex_batch(conn, [root / "a.gd"], root, "sync_cmd")

        # 传 a.gd：不包含 use_b.tscn 的问题
        r = scene_check(conn, root, paths=["a.gd"])
        b_problems = [p for p in r["regression"] if p["path"] == "use_b.tscn"]
        assert b_problems == []
    finally:
        conn.close()


def test_path_closure_full_scan_includes_all(tmp_path: Path) -> None:
    conn, root = _setup_two_scripts(tmp_path)
    try:
        (root / "a.gd").write_text("func work():\n\tpass\n", encoding="utf-8")
        writer.reindex_batch(conn, [root / "a.gd"], root, "sync_cmd")

        # 全量：包含 use_a.tscn
        r = scene_check(conn, root)
        assert any(p["path"] == "use_a.tscn" for p in r["regression"])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# coverage 字段
# ---------------------------------------------------------------------------


def test_coverage_fields(tmp_path: Path) -> None:
    conn, root = _setup_two_scripts(tmp_path)
    try:
        r = scene_check(conn, root)
        cov = r["coverage"]
        assert cov["files_total"] == 2
        assert cov["files_ok"] == 2
        assert cov["files_parse_failed"] == []
        assert cov["files_skipped_oversize"] == []
        assert cov["files_binary"] == []
        assert isinstance(cov["suppressed_checks"], list)
        assert isinstance(cov["rules_unavailable"], bool)
        assert isinstance(cov["scene_index_stale"], bool)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# summary 字段
# ---------------------------------------------------------------------------


def test_summary_fields(tmp_path: Path) -> None:
    conn, root = _setup_two_scripts(tmp_path)
    try:
        r = scene_check(conn, root)
        assert "error" in r["summary"]
        assert "by_code" in r["summary"]
        assert isinstance(r["summary"]["error"], int)
        assert isinstance(r["summary"]["by_code"], dict)
    finally:
        conn.close()
