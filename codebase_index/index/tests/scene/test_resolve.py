"""Step 2 的验收：L2 单文件语义模型。

见 codebase_index/NEXT_STEP.md Step 2 与 scenecheckfixture/README.md
的「测试时怎样算通过」。预期以夹具 README 为准，契约以 NEXT_STEP 为准。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from codeindex.scene import parse_scene
from codeindex.scene.resolve import resolve

FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "scenecheckfixture"

ALL_TSCN = sorted(FIXTURE_ROOT.rglob("*.tscn"))
REAL_DODGE = sorted(FIXTURE_ROOT.rglob("real_dodge_*.tscn"))
GODOT3_MATRIX = FIXTURE_ROOT / "godot3" / "generated_format_matrix.tscn"
GODOT4_MATRIX = FIXTURE_ROOT / "godot4" / "generated_format_matrix.tscn"

assert len(ALL_TSCN) == 8
assert len(REAL_DODGE) == 6


def _read_raw(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _resolve(path: Path):
    return resolve(parse_scene(_read_raw(path), str(path)))


# ---------------------------------------------------------------------------
# 验收 1：八个文件根数量都是 1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ALL_TSCN, ids=lambda p: p.name)
def test_corpus_single_root(path: Path) -> None:
    m = _resolve(path)
    assert len(m.root_paths) == 1, f"{path.name} 根数量 {len(m.root_paths)} != 1"


# ---------------------------------------------------------------------------
# 验收 2：node_by_path 与人工标注一致（多层嵌套、parent="."、同名兄弟）
# ---------------------------------------------------------------------------


def test_node_by_path_godot3_main() -> None:
    m = _resolve(FIXTURE_ROOT / "godot3" / "real_dodge_main.tscn")
    expected = {
        "Main",
        "ColorRect",
        "Player",
        "MobTimer",
        "ScoreTimer",
        "StartTimer",
        "StartPosition",
        "MobPath",
        "MobPath/MobSpawnLocation",
        "HUD",
        "Music",
        "DeathSound",
    }
    assert set(m.node_by_path) == expected
    # MobSpawnLocation 的父路径是 MobPath
    assert m.node_by_path["MobPath/MobSpawnLocation"].parent == "MobPath"
    assert m.node_by_path["MobPath/MobSpawnLocation"].type == "PathFollow2D"


def test_node_by_path_godot4_main() -> None:
    m = _resolve(FIXTURE_ROOT / "godot4" / "real_dodge_main.tscn")
    expected = {
        "Main",
        "ColorRect",
        "Player",
        "MobTimer",
        "ScoreTimer",
        "StartTimer",
        "StartPosition",
        "MobPath",
        "MobPath/MobSpawnLocation",
        "HUD",
        "Music",
        "DeathSound",
    }
    assert set(m.node_by_path) == expected
    assert m.node_by_path["MobPath/MobSpawnLocation"].parent == "MobPath"
    assert m.node_by_path["MobPath/MobSpawnLocation"].type == "PathFollow2D"


def test_node_by_path_godot3_player() -> None:
    m = _resolve(FIXTURE_ROOT / "godot3" / "real_dodge_player.tscn")
    expected = {"Player", "AnimatedSprite", "CollisionShape2D", "Trail"}
    assert set(m.node_by_path) == expected


def test_node_by_path_godot4_player() -> None:
    m = _resolve(FIXTURE_ROOT / "godot4" / "real_dodge_player.tscn")
    expected = {"Player", "AnimatedSprite2D", "CollisionShape2D", "Trail"}
    assert set(m.node_by_path) == expected


def test_node_by_path_godot3_hud() -> None:
    m = _resolve(FIXTURE_ROOT / "godot3" / "real_dodge_hud.tscn")
    expected = {"HUD", "ScoreLabel", "MessageLabel", "StartButton", "MessageTimer"}
    assert set(m.node_by_path) == expected


def test_node_by_path_godot4_hud() -> None:
    m = _resolve(FIXTURE_ROOT / "godot4" / "real_dodge_hud.tscn")
    expected = {"HUD", "ScoreLabel", "MessageLabel", "StartButton", "MessageTimer"}
    assert set(m.node_by_path) == expected


def test_node_by_path_godot3_matrix() -> None:
    m = _resolve(GODOT3_MATRIX)
    expected = {"Level", "Body", "Body/Placeholder", "Sprite"}
    assert set(m.node_by_path) == expected


def test_node_by_path_godot4_matrix() -> None:
    m = _resolve(GODOT4_MATRIX)
    expected = {
        "Ball",
        "CollisionShape3D",
        "MeshInstance3D",
        "OmniLight3D",
        "Camera3D",
        "Placeholder",
    }
    assert set(m.node_by_path) == expected


def test_synthetic_multilevel_and_same_name_siblings() -> None:
    """多层嵌套 + parent="." + 同名兄弟。"""
    text = (
        '[gd_scene format=3]\n'
        '[node name="Root" type="Node"]\n'
        '[node name="A" type="Node" parent="."]\n'
        '[node name="B" type="Node" parent="A"]\n'
        '[node name="C" type="Node" parent="A/B"]\n'
        '[node name="A2" type="Node" parent="."]\n'
        '[node name="B" type="Node" parent="A2"]\n'
    )
    m = resolve(parse_scene(text))
    assert set(m.node_by_path) == {"Root", "A", "A/B", "A/B/C", "A2", "A2/B"}
    assert m.node_by_path["A/B"].parent == "A"
    assert m.node_by_path["A2/B"].parent == "A2"
    assert m.node_by_path["A/B/C"].parent == "A/B"


# ---------------------------------------------------------------------------
# 验收 3：0、1、2 个根时 root_paths 长度正确
# ---------------------------------------------------------------------------


def test_root_count_zero() -> None:
    m = resolve(parse_scene('[gd_scene format=3]\n'))
    assert len(m.root_paths) == 0


def test_root_count_one() -> None:
    m = resolve(parse_scene('[gd_scene format=3]\n[node name="R" type="Node"]\n'))
    assert m.root_paths == ["R"]


def test_root_count_two() -> None:
    text = (
        '[gd_scene format=3]\n'
        '[node name="A" type="Node"]\n'
        '[node name="B" type="Node"]\n'
    )
    m = resolve(parse_scene(text))
    assert len(m.root_paths) == 2
    assert set(m.root_paths) == {"A", "B"}


# ---------------------------------------------------------------------------
# 验收 4：继承场景、instance=、instance_placeholder 的 unresolved_subtrees / is_inherited
# ---------------------------------------------------------------------------


def test_godot3_matrix_inherited() -> None:
    m = _resolve(GODOT3_MATRIX)
    assert m.is_inherited is True
    assert "." in m.unresolved_subtrees
    # 根节点 Level 带 instance
    assert "Level" in m.unresolved_subtrees
    # instance_placeholder
    assert "Body/Placeholder" in m.unresolved_subtrees


def test_godot4_matrix_inherited() -> None:
    m = _resolve(GODOT4_MATRIX)
    assert m.is_inherited is True
    assert "." in m.unresolved_subtrees
    assert "Ball" in m.unresolved_subtrees
    assert "Placeholder" in m.unresolved_subtrees


def test_real_dodge_main_instance_nodes() -> None:
    """两份 real_dodge_main 的 Player / HUD 是 instance 节点，标为 unresolved。"""
    for path in REAL_DODGE:
        if "main" not in path.name:
            continue
        m = _resolve(path)
        assert m.is_inherited is False
        assert "Player" in m.unresolved_subtrees
        assert "HUD" in m.unresolved_subtrees


def test_non_instance_files_no_unresolved() -> None:
    for name in ("real_dodge_hud.tscn", "real_dodge_player.tscn"):
        for path in REAL_DODGE:
            if path.name == name:
                m = _resolve(path)
                assert m.unresolved_subtrees == [], f"{path} 不应有 unresolved"
                assert m.is_inherited is False


# ---------------------------------------------------------------------------
# 验收 5：ext_use / sub_use 条数等于字符串之外的 ExtResource( / SubResource( 次数
# ---------------------------------------------------------------------------


def _count_calls_outside_strings(text: str, name: str) -> int:
    """去掉字符串内容后数 name( 出现次数。"""
    # 去掉 "..." 字符串（含转义）
    stripped = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)
    return len(re.findall(re.escape(name) + r"\s*\(", stripped))


@pytest.mark.parametrize("path", ALL_TSCN, ids=lambda p: p.name)
def test_ext_use_count(path: Path) -> None:
    text = _read_raw(path)
    m = _resolve(path)
    ext_use = sum(1 for r in m.refs if r.kind == "ext_use")
    expected = _count_calls_outside_strings(text, "ExtResource")
    assert ext_use == expected, f"{path.name} ext_use {ext_use} != {expected}"


@pytest.mark.parametrize("path", ALL_TSCN, ids=lambda p: p.name)
def test_sub_use_count(path: Path) -> None:
    text = _read_raw(path)
    m = _resolve(path)
    sub_use = sum(1 for r in m.refs if r.kind == "sub_use")
    expected = _count_calls_outside_strings(text, "SubResource")
    assert sub_use == expected, f"{path.name} sub_use {sub_use} != {expected}"


# ---------------------------------------------------------------------------
# 验收 6：resolve.py 不导入 os / pathlib / sqlite3
# ---------------------------------------------------------------------------


def test_resolve_no_forbidden_imports() -> None:
    src = Path(__file__).resolve().parents[2] / "src" / "codeindex" / "scene" / "resolve.py"
    text = src.read_text(encoding="utf-8")
    import ast

    tree = ast.parse(text)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for mod in ("os", "pathlib", "sqlite3"):
        assert mod not in imported, f"resolve.py 不应 import {mod}"


# ---------------------------------------------------------------------------
# 补充：ext / sub 表、连接、引用边种类
# ---------------------------------------------------------------------------


def test_ext_table_godot3() -> None:
    m = _resolve(FIXTURE_ROOT / "godot3" / "real_dodge_main.tscn")
    assert set(m.ext) == {"1", "2", "3", "4", "5", "6"}
    assert m.ext["1"].type == "Script"
    assert m.ext["1"].ref_path == "res://Main.gd"
    assert m.ext["2"].type == "PackedScene"


def test_ext_table_godot4() -> None:
    m = _resolve(FIXTURE_ROOT / "godot4" / "real_dodge_main.tscn")
    assert set(m.ext) == {"1_0r6n5", "2_50pww", "3_veqnc", "4_0qnje", "5_55d8h", "6_hp1r0"}
    assert m.ext["1_0r6n5"].type == "Script"
    assert m.ext["1_0r6n5"].uid == "uid://c4wt6ace7hycd"


def test_sub_table_godot3() -> None:
    m = _resolve(FIXTURE_ROOT / "godot3" / "real_dodge_player.tscn")
    assert set(m.sub) == {"1", "2", "3", "4", "5", "6", "7"}
    assert m.sub["1"].type == "SpriteFrames"


def test_sub_table_godot4() -> None:
    m = _resolve(FIXTURE_ROOT / "godot4" / "real_dodge_player.tscn")
    assert set(m.sub) == {"1", "2", "3", "4", "5", "6", "7"}
    assert m.sub["1"].type == "SpriteFrames"


def test_connections_godot3_main() -> None:
    m = _resolve(FIXTURE_ROOT / "godot3" / "real_dodge_main.tscn")
    assert len(m.conns) == 5
    methods = {c.method for c in m.conns}
    assert "game_over" in methods
    assert "new_game" in methods
    signals = {c.signal for c in m.conns}
    assert "hit" in signals
    assert "timeout" in signals
    assert "start_game" in signals


def test_ref_kinds_present() -> None:
    """确认各种引用边都被收集。"""
    m = _resolve(FIXTURE_ROOT / "godot3" / "real_dodge_main.tscn")
    kinds = {r.kind for r in m.refs}
    assert "node_type" in kinds
    assert "res_type" in kinds
    assert "ext_path" in kinds
    assert "ext_use" in kinds
    assert "sub_use" in kinds
    assert "script_ref" in kinds
    assert "instance" in kinds
    assert "conn_method" in kinds
    assert "conn_signal" in kinds


def test_script_ref_points_to_ext_id() -> None:
    m = _resolve(FIXTURE_ROOT / "godot3" / "real_dodge_main.tscn")
    script_refs = [r for r in m.refs if r.kind == "script_ref"]
    assert len(script_refs) == 1
    assert script_refs[0].value == "1"  # Main.gd 的 ext id
    assert script_refs[0].node_path == "Main"


def test_prop_key_on_scripted_node() -> None:
    """挂了脚本的节点，属性键全部入库。"""
    m = _resolve(FIXTURE_ROOT / "godot3" / "real_dodge_main.tscn")
    prop_keys = [r for r in m.refs if r.kind == "prop_key" and r.node_path == "Main"]
    keys = {r.value for r in prop_keys}
    assert "mob_scene" in keys


def test_group_ref() -> None:
    m = _resolve(GODOT3_MATRIX)
    groups = [r for r in m.refs if r.kind == "group"]
    assert {r.value for r in groups} == {"player", "hurtbox"}


def test_nodepath_ref() -> None:
    m = _resolve(GODOT4_MATRIX)
    nodepaths = [r for r in m.refs if r.kind == "nodepath"]
    values = {r.value for r in nodepaths}
    assert ".." in values  # follow_node = NodePath("..")
