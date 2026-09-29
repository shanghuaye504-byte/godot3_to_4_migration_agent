"""场景不变量（G2.2/G2.3/G3.1）与判据 5（改名一致性）的验收测试。

验收条目见 NEXT_STEP.md「Step 7」。测试直接调用
`inline_tools.editandfixguard.scene_names`，不经过 edit()；
不把 .tscn 送进 tree-sitter，不写 index.db。
"""

from __future__ import annotations

import importlib
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _import(name: str):
    sys.path.insert(0, str(REPO_ROOT))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(REPO_ROOT))


scene_names = _import("inline_tools.editandfixguard.scene_names")
check_scene_invariants = scene_names.check_scene_invariants
check_rename_consistency = scene_names.check_rename_consistency

FILE = "res://main.tscn"

VALID_SCENE = """[gd_scene format=3 uid="uid://abc"]

[node name="Root" type="Node2D"]
"""


class TestSceneSyntaxRegression:
    """G2.2：post 的 P_* 真包含 pre → SCENE_SYNTAX_REGRESSION。"""

    def test_new_parse_problem_rejected(self) -> None:
        bad_post = VALID_SCENE + "\n[node broken\n"  # 方括号未闭合 → P_*
        result = check_scene_invariants(FILE, VALID_SCENE, bad_post)
        assert not result.ok
        assert any(v.id == scene_names.SCENE_SYNTAX_REGRESSION for v in result.violations)

    def test_preexisting_problem_not_rejected(self) -> None:
        # pre 和 post 有同样的 P_*，不是「新出现」
        bad = VALID_SCENE + "\n[node broken\n"
        result = check_scene_invariants(FILE, bad, bad)
        assert not any(v.id == scene_names.SCENE_SYNTAX_REGRESSION for v in result.violations)


class TestConflictMarker:
    """G2.3：post 新出现 <<<<<<< / ======= / >>>>>>> 而 pre 没有 → CONFLICT_MARKER。"""

    def test_new_conflict_marker_rejected(self) -> None:
        post = VALID_SCENE + "\n<<<<<<< HEAD\n=======\n>>>>>>> branch\n"
        result = check_scene_invariants(FILE, VALID_SCENE, post)
        assert not result.ok
        assert any(v.id == scene_names.CONFLICT_MARKER for v in result.violations)

    def test_preexisting_marker_not_rejected(self) -> None:
        both = VALID_SCENE + "\n<<<<<<< HEAD\n"
        result = check_scene_invariants(FILE, both, both)
        assert not any(v.id == scene_names.CONFLICT_MARKER for v in result.violations)


class TestSceneInvariantRegression:
    """G3.1：post 的 L4 ERROR 指纹真包含 pre → SCENE_INVARIANT_REGRESSION；弃权项不算。"""

    def test_new_l4_error_rejected(self) -> None:
        # 没有 gd_scene 头 → E_PARSE_* 或 E_NO_SCENE_ROOT 之类 L4 ERROR
        bad_post = "[node name=\"Root\" type=\"Node2D\"]\n"
        result = check_scene_invariants(FILE, VALID_SCENE, bad_post)
        assert not result.ok
        assert any(v.id == scene_names.SCENE_INVARIANT_REGRESSION for v in result.violations)

    def test_same_l4_not_rejected(self) -> None:
        bad = "[node name=\"Root\" type=\"Node2D\"]\n"
        result = check_scene_invariants(FILE, bad, bad)
        assert not any(v.id == scene_names.SCENE_INVARIANT_REGRESSION for v in result.violations)


class TestCreateTreatsOwnProblemsAsRegression:
    """create 时 pre 为空，新文件自身的 error、P_*、L4 ERROR 视为回归。"""

    def test_create_with_parse_problem_rejected(self) -> None:
        bad_post = "[node broken\n"
        result = check_scene_invariants(FILE, "", bad_post)
        assert not result.ok
        assert any(v.id == scene_names.SCENE_SYNTAX_REGRESSION for v in result.violations)

    def test_create_with_l4_error_rejected(self) -> None:
        bad_post = "[node name=\"Root\" type=\"Node2D\"]\n"  # 缺 gd_scene 头
        result = check_scene_invariants(FILE, "", bad_post)
        assert not result.ok
        assert any(v.id == scene_names.SCENE_INVARIANT_REGRESSION for v in result.violations)

    def test_create_clean_scene_passes(self) -> None:
        result = check_scene_invariants(FILE, "", VALID_SCENE)
        assert result.ok, result.violations


class TestRenameConsistency:
    """判据 5：.gd 改名后旧名不得仍被场景引用。"""

    def _index_db(self, tmp_path: Path) -> Path:
        db = tmp_path / "index.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE scene_conn (path TEXT, signal TEXT, from_path TEXT, to_path TEXT, method TEXT)")
        conn.execute("CREATE TABLE scene_refs (path TEXT, line INT, col INT, kind TEXT, symbol TEXT, node_path TEXT, target_file TEXT, detail TEXT)")
        conn.execute("INSERT INTO scene_conn VALUES ('res://main.tscn', 'died', '.', '.', '_on_died')")
        conn.execute("INSERT INTO scene_refs VALUES ('res://main.tscn', 12, 5, 'script_class', 'Player', '.', 'res://player.gd', '')")
        conn.execute("INSERT INTO scene_refs VALUES ('res://main.tscn', 20, 1, 'other_kind', 'Ignored', '.', '', '')")
        conn.commit()
        conn.close()
        return db

    def test_index_hit_is_warn_with_path(self, tmp_path: Path) -> None:
        db = self._index_db(tmp_path)
        result = check_rename_consistency(
            tmp_path, renamed={"died": "perished", "Player": "Character"}, db_path=db
        )
        assert result.ok  # warn 不 block
        hits = [v for v in result.violations if v.id == scene_names.INCONSISTENT_RENAME]
        assert hits
        assert all(not v.block for v in hits)
        assert any(v.file == "res://main.tscn" for v in hits)

    def test_scene_refs_kind_filtered(self, tmp_path: Path) -> None:
        # kind='other_kind' 的 scene_refs 行不算命中
        db = self._index_db(tmp_path)
        result = check_rename_consistency(tmp_path, renamed={"Ignored": "NewName"}, db_path=db)
        assert not any(v.id == scene_names.INCONSISTENT_RENAME for v in result.violations)

    def test_missing_index_falls_back_to_grep(self, tmp_path: Path) -> None:
        # 索引库不存在：只跑 grep，不因此拒绝
        (tmp_path / "main.tscn").write_text(VALID_SCENE + "\n# old_name died\n", encoding="utf-8")
        result = check_rename_consistency(
            tmp_path, renamed={"died": "perished"}, db_path=tmp_path / "missing.db"
        )
        assert result.ok  # grep 命中是 warn，不 block
        assert any(v.id == scene_names.INCONSISTENT_RENAME for v in result.violations)

    def test_grep_word_boundary(self, tmp_path: Path) -> None:
        # 「diedx」不应命中「died」的词边界搜索
        (tmp_path / "main.tscn").write_text(VALID_SCENE + "\n# signal diedx\n", encoding="utf-8")
        result = check_rename_consistency(
            tmp_path, renamed={"died": "perished"}, db_path=None
        )
        assert not any(v.id == scene_names.INCONSISTENT_RENAME for v in result.violations)

    def test_grep_hit_has_path_and_line(self, tmp_path: Path) -> None:
        (tmp_path / "main.tscn").write_text(VALID_SCENE + "\n# old signal died here\n", encoding="utf-8")
        result = check_rename_consistency(tmp_path, renamed={"died": "perished"}, db_path=None)
        hits = [v for v in result.violations if v.id == scene_names.INCONSISTENT_RENAME]
        assert hits
        assert all(v.file for v in hits)
        assert all(v.line is not None for v in hits)
