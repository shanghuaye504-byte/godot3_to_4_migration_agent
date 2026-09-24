"""Step 5 快照与 E_MEMBER_GONE 验收。

见 codebase_index/NEXT_STEP.md Step 5。
"""

from __future__ import annotations

from pathlib import Path

from codeindex.db import connection, writer
from codeindex.scene.baseline import freeze_baseline
from codeindex.scene.check import scene_check
from codeindex.scene.rules import check_scene


def _make_project(tmp_path: Path, gd_text: str, tscn_text: str):
    """建一个 .gd + .tscn 的临时工程，冻结 baseline，返回 (conn, root)。"""
    (tmp_path / "player.gd").write_text(gd_text, encoding="utf-8")
    (tmp_path / "level.tscn").write_text(tscn_text, encoding="utf-8")
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    writer.reindex_batch(
        conn, [tmp_path / "player.gd", tmp_path / "level.tscn"], tmp_path, "sync_cmd"
    )
    # 冻结
    text = (tmp_path / "level.tscn").read_bytes().decode()
    r = check_scene(
        text, "level.tscn",
        repo_classes=_repo_classes(conn),
        file_exists=lambda rf: (tmp_path / rf).exists(),
    )
    freeze_baseline(conn, r.problems)
    return conn, tmp_path


def _repo_classes(conn) -> set[str]:
    return {
        row[0]
        for row in conn.execute("SELECT DISTINCT name FROM symbols WHERE kind = 'class'")
    }


_GD = "class_name Player\nextends CharacterBody2D\nfunc _ready():\n\tpass\nfunc take_damage():\n\tpass\n"
_TSCN = (
    '[gd_scene load_steps=2 format=3]\n'
    '\n'
    '[ext_resource type="Script" path="res://player.gd" id="1"]\n'
    '\n'
    '[node name="Level" type="Node"]\n'
    '\n'
    '[node name="Hero" type="Player" parent="."]\n'
    'script = ExtResource("1")\n'
    '\n'
    '[connection signal="hit" from="Hero" to="." method="take_damage"]\n'
)


# ---------------------------------------------------------------------------
# 三分法：修好、弄坏、留下
# ---------------------------------------------------------------------------


def test_three_way_diff(tmp_path: Path) -> None:
    conn, root = _make_project(tmp_path, _GD, _TSCN)
    try:
        # 当前应该零 regression、零 pre_existing、零 fixed
        r = scene_check(conn, root)
        assert r["regression"] == []
        assert r["pre_existing"]["count"] == 0
        assert r["fixed"] == []

        # 弄坏：改名 class_name
        (root / "player.gd").write_text(
            "class_name Hero\nextends CharacterBody2D\nfunc _ready():\n\tpass\nfunc take_damage():\n\tpass\n",
            encoding="utf-8",
        )
        writer.reindex_batch(conn, [root / "player.gd"], root, "sync_cmd")
        r2 = scene_check(conn, root)
        assert len(r2["regression"]) == 1
        assert r2["regression"][0]["code"] == "E_MEMBER_GONE"
        assert "Player" in r2["regression"][0]["subject"]

        # 修好：场景改成新名字
        (root / "level.tscn").write_text(
            _TSCN.replace('type="Player"', 'type="Hero"'), encoding="utf-8"
        )
        writer.reindex_batch(conn, [root / "level.tscn"], root, "sync_cmd")
        r3 = scene_check(conn, root)
        assert r3["regression"] == []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 文件头插入 100 行后 fingerprint 不变
# ---------------------------------------------------------------------------


def test_line_shift_preserves_fingerprint(tmp_path: Path) -> None:
    conn, root = _make_project(tmp_path, _GD, _TSCN)
    try:
        # 当前零 regression
        r1 = scene_check(conn, root)
        assert r1["regression"] == []

        # 文件头插 100 行注释
        original = (root / "level.tscn").read_text(encoding="utf-8")
        padded = "\n".join(f"; padding {i}" for i in range(100)) + "\n" + original
        (root / "level.tscn").write_text(padded, encoding="utf-8")
        writer.reindex_batch(conn, [root / "level.tscn"], root, "sync_cmd")

        r2 = scene_check(conn, root)
        assert r2["regression"] == []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# class_name 改名 → regression；场景改成新名后消失
# ---------------------------------------------------------------------------


def test_class_rename_produces_regression(tmp_path: Path) -> None:
    conn, root = _make_project(tmp_path, _GD, _TSCN)
    try:
        (root / "player.gd").write_text(
            "class_name Hero\nextends CharacterBody2D\nfunc _ready():\n\tpass\nfunc take_damage():\n\tpass\n",
            encoding="utf-8",
        )
        writer.reindex_batch(conn, [root / "player.gd"], root, "sync_cmd")
        r = scene_check(conn, root)
        member_gone = [p for p in r["regression"] if p["code"] == "E_MEMBER_GONE"]
        assert len(member_gone) == 1
        assert "class:Player" in member_gone[0]["subject"]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 函数改名 → regression；_ready 不报
# ---------------------------------------------------------------------------


def test_func_rename_produces_regression(tmp_path: Path) -> None:
    conn, root = _make_project(tmp_path, _GD, _TSCN)
    try:
        (root / "player.gd").write_text(
            "class_name Player\nextends CharacterBody2D\nfunc _ready():\n\tpass\nfunc on_hit():\n\tpass\n",
            encoding="utf-8",
        )
        writer.reindex_batch(conn, [root / "player.gd"], root, "sync_cmd")
        r = scene_check(conn, root)
        member_gone = [p for p in r["regression"] if p["code"] == "E_MEMBER_GONE"]
        assert len(member_gone) == 1
        assert "func:take_damage" in member_gone[0]["subject"]
        # _ready 不报
        assert not any("_ready" in p["subject"] for p in r["regression"])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 引擎类型不产生 E_MEMBER_GONE
# ---------------------------------------------------------------------------


def test_engine_types_no_member_gone(tmp_path: Path) -> None:
    tscn = (
        '[gd_scene format=3]\n'
        '[node name="R" type="Node"]\n'
        '[node name="S" type="Sprite2D" parent="."]\n'
        '[node name="C" type="CharacterBody2D" parent="."]\n'
    )
    (tmp_path / "empty.gd").write_text("extends Node\n", encoding="utf-8")
    (tmp_path / "level.tscn").write_text(tscn, encoding="utf-8")
    db = tmp_path / "index.db"
    conn = connection.connect_rw(db)
    try:
        writer.reindex_batch(
            conn, [tmp_path / "empty.gd", tmp_path / "level.tscn"], tmp_path, "sync_cmd"
        )
        freeze_baseline(conn, [])
        r = scene_check(conn, tmp_path)
        member_gone = [p for p in r["regression"] if p["code"] == "E_MEMBER_GONE"]
        assert member_gone == []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 脚本语法失败 → 弃权
# ---------------------------------------------------------------------------


def test_broken_script_suppresses(tmp_path: Path) -> None:
    conn, root = _make_project(tmp_path, _GD, _TSCN)
    try:
        (root / "player.gd").write_text("func broken(:\n", encoding="utf-8")
        writer.reindex_batch(conn, [root / "player.gd"], root, "sync_cmd")
        r = scene_check(conn, root)
        member_gone = [p for p in r["regression"] if p["code"] == "E_MEMBER_GONE"]
        assert member_gone == []
        assert any("语法失败" in s["reason"] for s in r["coverage"]["suppressed_checks"])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 冻结后再索引，member_baseline 不跟随
# ---------------------------------------------------------------------------


def test_baseline_not_updated_by_reindex(tmp_path: Path) -> None:
    conn, root = _make_project(tmp_path, _GD, _TSCN)
    try:
        # 冻结时的成员
        frozen = {
            (row[0], row[1], row[2])
            for row in conn.execute("SELECT script_path, kind, name FROM scene_member_baseline")
        }
        assert ("player.gd", "class", "Player") in frozen
        assert ("player.gd", "func", "take_damage") in frozen

        # 改名后重新索引
        (root / "player.gd").write_text(
            "class_name Hero\nextends CharacterBody2D\nfunc _ready():\n\tpass\n",
            encoding="utf-8",
        )
        writer.reindex_batch(conn, [root / "player.gd"], root, "sync_cmd")

        # member_baseline 仍是冻结时的
        after = {
            (row[0], row[1], row[2])
            for row in conn.execute("SELECT script_path, kind, name FROM scene_member_baseline")
        }
        assert after == frozen
    finally:
        conn.close()
