"""Step 3 的 find-symbol 场景引用验收。

见 codebase_index/NEXT_STEP.md Step 3。
"""

from __future__ import annotations

from pathlib import Path

from codeindex.db import connection, queries, writer


def _make_project(tmp_path: Path):
    """建一个带场景和脚本的临时工程。"""
    (tmp_path / "level.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n'
        '\n'
        '[ext_resource type="Script" path="res://player.gd" id="1"]\n'
        '\n'
        '[node name="Level" type="Node"]\n'
        '\n'
        '[node name="Hero" type="Player" parent="."]\n'
        'script = ExtResource("1")\n'
        'speed = 100\n',
        encoding="utf-8",
    )
    (tmp_path / "player.gd").write_text(
        "class_name Player\n"
        "extends CharacterBody2D\n"
        "func take_damage():\n"
        "\tpass\n",
        encoding="utf-8",
    )
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    writer.reindex_batch(
        conn,
        [tmp_path / "level.tscn", tmp_path / "player.gd"],
        tmp_path,
        "sync_cmd",
    )
    return conn, tmp_path


# ---------------------------------------------------------------------------
# class_name 在场景里被引用
# ---------------------------------------------------------------------------


def test_class_name_brings_scene_usages(tmp_path: Path) -> None:
    conn, _ = _make_project(tmp_path)
    try:
        r = queries.find_symbol(conn, "Player")
        assert len(r["matches"]) == 1
        assert r["scene_usage_count"] > 0
        kinds = {u["kind"] for u in r["scene_usages"]}
        assert "node_type" in kinds  # type="Player"
        assert "script_ref" in kinds  # script = ExtResource("1")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# func 在场景里被引用（prop_key）
# ---------------------------------------------------------------------------


def test_func_brings_scene_usages(tmp_path: Path) -> None:
    conn, _ = _make_project(tmp_path)
    try:
        r = queries.find_symbol(conn, "take_damage")
        assert len(r["matches"]) == 1
        # take_damage 不在场景文本里，但 player.gd 被 script_ref 引用
        # target_file 支应带回
        assert r["scene_usage_count"] > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 脚本路径通过 target_file 反查
# ---------------------------------------------------------------------------


def test_script_path_via_target_file(tmp_path: Path) -> None:
    conn, _ = _make_project(tmp_path)
    try:
        r = queries.find_symbol(conn, "Player")
        target_kinds = {u["kind"] for u in r["scene_usages"]}
        assert "ext_path" in target_kinds
        assert "script_ref" in target_kinds
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# scene_usage_count 是全表计数
# ---------------------------------------------------------------------------


def test_scene_usage_count_is_full_count(tmp_path: Path) -> None:
    conn, _ = _make_project(tmp_path)
    try:
        r = queries.find_symbol(conn, "Player")
        # count 不受 LIMIT 50 影响
        assert r["scene_usage_count"] >= len(r["scene_usages"])
        assert r["scene_usage_truncated"] is False
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 符号已从 .gd 删除、场景仍引用
# ---------------------------------------------------------------------------


def test_symbol_deleted_but_scene_still_references(tmp_path: Path) -> None:
    conn, root = _make_project(tmp_path)
    try:
        # 删掉 class_name Player
        (root / "player.gd").write_text("extends CharacterBody2D\n", encoding="utf-8")
        writer.reindex_batch(conn, [root / "player.gd"], root, "sync_cmd")
        r = queries.find_symbol(conn, "Player")
        assert r["matches"] == []
        assert len(r["scene_usages"]) > 0
        assert r["scene_usage_count"] > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 无场景引用时 matches 字段不变
# ---------------------------------------------------------------------------


def test_no_scene_reference_matches_unchanged(tmp_path: Path) -> None:
    """没有场景引用时，matches 的字段与改之前一致，line 仍是 0-based。"""
    (tmp_path / "lonely.gd").write_text(
        "class_name Lonely\nfunc work():\n\tpass\n", encoding="utf-8"
    )
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    try:
        writer.reindex_batch(conn, [tmp_path / "lonely.gd"], tmp_path, "sync_cmd")
        r = queries.find_symbol(conn, "Lonely")
        assert len(r["matches"]) == 1
        m = r["matches"][0]
        assert set(m.keys()) == {"path", "name", "kind", "line", "end_line", "class_name", "signature"}
        assert m["line"] == 0  # 0-based
        assert r["scene_usages"] == []
        assert r["scene_usage_count"] == 0
        assert r["scene_usage_truncated"] is False
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# scene_usages 的 line 是 1-based
# ---------------------------------------------------------------------------


def test_scene_usages_line_is_1_based(tmp_path: Path) -> None:
    conn, _ = _make_project(tmp_path)
    try:
        r = queries.find_symbol(conn, "Player")
        for u in r["scene_usages"]:
            assert u["line"] >= 1, f"scene_usages line 应 1-based，得到 {u['line']}"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 两边都空
# ---------------------------------------------------------------------------


def test_both_empty(tmp_path: Path) -> None:
    conn, _ = _make_project(tmp_path)
    try:
        r = queries.find_symbol(conn, "NonExistent")
        assert r["matches"] == []
        assert r["scene_usages"] == []
        assert r["scene_usage_count"] == 0
    finally:
        conn.close()
