"""Step 4 的验收：L4 ERROR。

见 codebase_index/NEXT_STEP.md Step 4 与 scenecheckfixture/README.md。
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from codeindex.scene.rules import check_scene

FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "scenecheckfixture"

GODOT3_FILES = sorted((FIXTURE_ROOT / "godot3").glob("*.tscn"))
GODOT4_FILES = sorted((FIXTURE_ROOT / "godot4").glob("*.tscn"))
GODOT3_MATRIX = FIXTURE_ROOT / "godot3" / "generated_format_matrix.tscn"
GODOT4_MATRIX = FIXTURE_ROOT / "godot4" / "generated_format_matrix.tscn"


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _make_rules_db(tmp_path: Path, classes: list[str]) -> Path:
    db = tmp_path / "rules.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE rules (old_symbol TEXT, new_symbol TEXT, symbol_kind TEXT)")
    for c in classes:
        conn.execute("INSERT INTO rules VALUES (?, ?, 'class')", (c, c + "_new"))
    conn.commit()
    conn.close()
    return db


# ---------------------------------------------------------------------------
# 夹具：四个 Godot 3 文件都有 E_NOT_CONVERTED
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", GODOT3_FILES, ids=lambda p: p.name)
def test_godot3_has_e_not_converted(path: Path) -> None:
    r = check_scene(_read(path), path.name)
    codes = [p.code for p in r.problems]
    assert "E_NOT_CONVERTED" in codes, f"{path.name} 应有 E_NOT_CONVERTED"


@pytest.mark.parametrize("path", GODOT4_FILES, ids=lambda p: p.name)
def test_godot4_no_e_not_converted(path: Path) -> None:
    r = check_scene(_read(path), path.name)
    codes = [p.code for p in r.problems]
    assert "E_NOT_CONVERTED" not in codes


# ---------------------------------------------------------------------------
# Godot 4 三个真实文件没有语法级 ERROR
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [p for p in GODOT4_FILES if "real_dodge" in p.name],
    ids=lambda p: p.name,
)
def test_godot4_real_files_no_parse_errors(path: Path) -> None:
    r = check_scene(_read(path), path.name)
    parse_errors = [p for p in r.problems if p.code.startswith("E_PARSE_")]
    assert parse_errors == [], f"{path.name} 有语法级 ERROR: {[(p.code, p.message) for p in parse_errors]}"


# ---------------------------------------------------------------------------
# 每一类 E 级故障注入检出率 100%
# ---------------------------------------------------------------------------


class TestInjections:
    def test_e_no_scene_root(self) -> None:
        r = check_scene('[gd_scene format=3]\n', 't.tscn')
        assert any(p.code == "E_NO_SCENE_ROOT" for p in r.problems)

    def test_e_multiple_roots(self) -> None:
        text = '[gd_scene format=3]\n[node name="A" type="Node"]\n[node name="B" type="Node"]\n'
        r = check_scene(text, 't.tscn')
        assert any(p.code == "E_MULTIPLE_ROOTS" for p in r.problems)

    def test_e_ext_id_undeclared(self) -> None:
        text = '[gd_scene format=3]\n[node name="A" type="Node"]\nx = ExtResource("99")\n'
        r = check_scene(text, 't.tscn')
        assert any(p.code == "E_EXT_ID_UNDECLARED" for p in r.problems)

    def test_e_sub_id_undeclared(self) -> None:
        text = '[gd_scene format=3]\n[node name="A" type="Node"]\nx = SubResource("99")\n'
        r = check_scene(text, 't.tscn')
        assert any(p.code == "E_SUB_ID_UNDECLARED" for p in r.problems)

    def test_e_duplicate_ext_id(self) -> None:
        text = (
            '[gd_scene format=3]\n'
            '[ext_resource path="res://a.gd" type="Script" id="1"]\n'
            '[ext_resource path="res://b.gd" type="Script" id="1"]\n'
            '[node name="A" type="Node"]\n'
        )
        r = check_scene(text, 't.tscn')
        assert any(p.code == "E_DUPLICATE_EXT_ID" for p in r.problems)

    def test_e_duplicate_sub_id(self) -> None:
        text = (
            '[gd_scene format=3]\n'
            '[sub_resource type="Resource" id="1"]\n'
            '[sub_resource type="Resource" id="1"]\n'
            '[node name="A" type="Node"]\n'
        )
        r = check_scene(text, 't.tscn')
        assert any(p.code == "E_DUPLICATE_SUB_ID" for p in r.problems)

    def test_e_node_parent_missing(self) -> None:
        text = '[gd_scene format=3]\n[node name="A" type="Node"]\n[node name="B" type="Node" parent="Ghost"]\n'
        r = check_scene(text, 't.tscn')
        assert any(p.code == "E_NODE_PARENT_MISSING" for p in r.problems)

    def test_e_node_no_type(self) -> None:
        text = '[gd_scene format=3]\n[node name="A" type="Node"]\n[node name="B" parent="."]\n'
        r = check_scene(text, 't.tscn')
        assert any(p.code == "E_NODE_NO_TYPE" for p in r.problems)

    def test_e_conn_node_missing(self) -> None:
        text = (
            '[gd_scene format=3]\n'
            '[node name="A" type="Node"]\n'
            '[connection signal="x" from="Ghost" to="." method="y"]\n'
        )
        r = check_scene(text, 't.tscn')
        assert any(p.code == "E_CONN_NODE_MISSING" for p in r.problems)

    def test_e_script_ref_not_script(self) -> None:
        text = (
            '[gd_scene load_steps=2 format=3]\n'
            '[ext_resource path="res://image.png" type="Texture" id="1"]\n'
            '[node name="A" type="Node"]\n'
            'script = ExtResource("1")\n'
        )
        r = check_scene(text, 't.tscn')
        assert any(p.code == "E_SCRIPT_REF_NOT_SCRIPT" for p in r.problems)

    def test_e_not_converted(self) -> None:
        r = check_scene('[gd_scene format=2]\n[node name="A" type="Node"]\n', 't.tscn')
        assert any(p.code == "E_NOT_CONVERTED" for p in r.problems)

    def test_e_instance_cycle(self) -> None:
        text = (
            '[gd_scene load_steps=2 format=3]\n'
            '[ext_resource path="res://t.tscn" type="PackedScene" id="1"]\n'
            '[node name="A" type="Node"]\n'
            '[node name="B" parent="." instance=ExtResource("1")]\n'
        )
        r = check_scene(text, 't.tscn')
        assert any(p.code == "E_INSTANCE_CYCLE" for p in r.problems)

    def test_subject_no_line_number(self) -> None:
        text = '[gd_scene format=3]\n[node name="A" type="Node"]\n[node name="B" type="Node" parent="Ghost"]\n'
        r = check_scene(text, 't.tscn')
        for p in r.problems:
            assert not any(c.isdigit() for c in p.subject.split(":")[-1].split("@")[0]) or True
            # subject 不含行号：检查 subject 里没有纯数字段
            import re
            assert not re.search(r"\b\d{2,}\b", p.subject), f"subject 含行号: {p.subject}"


# ---------------------------------------------------------------------------
# 弃权：注入放进实例子树或继承场景
# ---------------------------------------------------------------------------


class TestSuppression:
    def test_inherited_scene_suppresses_node_errors(self) -> None:
        text = (
            '[gd_scene load_steps=2 format=3]\n'
            '[ext_resource path="res://base.tscn" type="PackedScene" id="1"]\n'
            '[node name="Root" type="Node" instance=ExtResource("1")]\n'
            '[node name="Child" type="Node" parent="Ghost"]\n'
        )
        r = check_scene(text, 't.tscn')
        errors = [p for p in r.problems if p.code == "E_NODE_PARENT_MISSING"]
        assert errors == [], "继承场景里不应报 E_NODE_PARENT_MISSING"
        assert any(s["node_path"] is not None for s in r.suppressed_checks)

    def test_instance_subtree_suppresses(self) -> None:
        text = (
            '[gd_scene load_steps=2 format=3]\n'
            '[ext_resource path="res://other.tscn" type="PackedScene" id="1"]\n'
            '[node name="Root" type="Node"]\n'
            '[node name="Sub" parent="." instance=ExtResource("1")]\n'
            '[node name="Deep" type="Node" parent="Sub/Ghost"]\n'
        )
        r = check_scene(text, 't.tscn')
        errors = [p for p in r.problems if p.code == "E_NODE_PARENT_MISSING"]
        assert errors == []
        assert any("Sub" in (s["node_path"] or "") for s in r.suppressed_checks)

    def test_instance_placeholder_suppresses(self) -> None:
        text = (
            '[gd_scene format=3]\n'
            '[node name="Root" type="Node"]\n'
            '[node name="PH" parent="." instance_placeholder="res://opt.tscn"]\n'
            '[node name="Deep" type="Node" parent="PH/Ghost"]\n'
        )
        r = check_scene(text, 't.tscn')
        errors = [p for p in r.problems if p.code == "E_NODE_PARENT_MISSING"]
        assert errors == []


# ---------------------------------------------------------------------------
# E_UNMIGRATED_TYPE
# ---------------------------------------------------------------------------


class TestUnmigratedType:
    def test_with_rules_db(self, tmp_path: Path) -> None:
        db = _make_rules_db(tmp_path, ["KinematicBody2D"])
        text = '[gd_scene format=3]\n[node name="A" type="Node"]\n[node name="B" type="KinematicBody2D" parent="."]\n'
        r = check_scene(text, 't.tscn', rules_db_path=db)
        assert any(p.code == "E_UNMIGRATED_TYPE" for p in r.problems)
        assert r.rules_unavailable is False

    def test_without_rules_db(self) -> None:
        text = '[gd_scene format=3]\n[node name="A" type="Node"]\n[node name="B" type="KinematicBody2D" parent="."]\n'
        r = check_scene(text, 't.tscn')
        assert not any(p.code == "E_UNMIGRATED_TYPE" for p in r.problems)
        assert r.rules_unavailable is True

    def test_repo_class_exempts(self, tmp_path: Path) -> None:
        db = _make_rules_db(tmp_path, ["KinematicBody2D"])
        text = '[gd_scene format=3]\n[node name="A" type="Node"]\n[node name="B" type="KinematicBody2D" parent="."]\n'
        r = check_scene(text, 't.tscn', rules_db_path=db, repo_classes={"KinematicBody2D"})
        assert not any(p.code == "E_UNMIGRATED_TYPE" for p in r.problems)

    def test_godot3_matrix_with_rules(self, tmp_path: Path) -> None:
        """夹具 godot3 matrix 有 KinematicBody2D，但 is_inherited=True，所以弃权。"""
        db = _make_rules_db(tmp_path, ["KinematicBody2D"])
        r = check_scene(_read(GODOT3_MATRIX), GODOT3_MATRIX.name, rules_db_path=db)
        unmigrated = [p for p in r.problems if p.code == "E_UNMIGRATED_TYPE"]
        assert unmigrated == [], "继承场景里 E_UNMIGRATED_TYPE 应弃权"
        assert any("KinematicBody2D" in s["reason"] or "unmigrated" in s["reason"].lower()
                   for s in r.suppressed_checks)


# ---------------------------------------------------------------------------
# fingerprint 稳定性
# ---------------------------------------------------------------------------


def test_fingerprint_stable_across_line_shifts() -> None:
    text = '[gd_scene format=3]\n[node name="A" type="Node"]\n[node name="B" type="Node" parent="Ghost"]\n'
    r1 = check_scene(text, 't.tscn')
    padded = "; comment\n\n\n" + text
    r2 = check_scene(padded, 't.tscn')
    fp1 = {p.fingerprint for p in r1.problems}
    fp2 = {p.fingerprint for p in r2.problems}
    assert fp1 == fp2


def test_idempotent() -> None:
    text = '[gd_scene format=3]\n[node name="A" type="Node"]\n[node name="B" type="Node" parent="Ghost"]\n'
    r1 = check_scene(text, 't.tscn')
    r2 = check_scene(text, 't.tscn')
    assert [p.fingerprint for p in r1.problems] == [p.fingerprint for p in r2.problems]
