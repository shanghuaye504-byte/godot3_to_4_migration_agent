"""判据 1（爆炸半径）的验收测试。

验收条目见 NEXT_STEP.md「Step 3 判据 1 爆炸半径」。测试直接调用
`inline_tools.editandfixguard.guard.check_blast_radius`，输入是 Step 2
`apply_hunks` 产出的规范 udiff。不经过尚未实现的 edit()。
"""

from __future__ import annotations

import importlib
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _import(name: str):
    sys.path.insert(0, str(REPO_ROOT))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(REPO_ROOT))


anchor = _import("inline_tools.editandfixguard.anchor")
guard = _import("inline_tools.editandfixguard.guard")

Hunk = anchor.Hunk
apply_hunks = anchor.apply_hunks
check_blast_radius = guard.check_blast_radius
OUTSIDE_BLAST_RADIUS = guard.OUTSIDE_BLAST_RADIUS

# 30 行的 .gd 文件，根因在第 15 行
OLD_LINES = [f"s{i}n" for i in range(1, 31)]
OLD_TEXT = "\n".join(OLD_LINES)


def _udiff_for(path: str, old_text: str, hunks: list) -> str:
    """用 Step 2 的 apply_hunks 产出 tofile 为指定路径的 udiff。"""
    result = apply_hunks(old_text, hunks)
    assert result["ok"] is True, result
    return result["udiff"].replace("b/file", f"b/{path}")


def _root(res_path: str, line: int | None) -> dict:
    return {"res_path": res_path, "line": line, "kind": "parse_error"}


def _pointer(target: str) -> dict:
    return {"res_path": "res://referrer.gd", "target_res_path": target, "role": "pointer"}


class TestParseUdiffChangedLines:
    """用 Step 2 的 udiff 行号做输入：hunk 头 1-based，取新文件侧区间。"""

    def test_changed_lines_from_hunk_header(self) -> None:
        # 替换第 15 行：n=3 时新文件侧从第 12 行起 7 行
        udiff = _udiff_for("player.gd", OLD_TEXT, [Hunk(remove=["s15n"], insert=["S15N"])])
        changed = guard.parse_udiff_changed_lines(udiff)
        assert changed == {"player.gd": [15]}


class TestRootCauseRadius:
    """C = 根因 (res_path, line) ∪ ...；根因文件上 |行差| > 15 拒绝；N = 15。"""

    def test_change_at_root_line_passes(self) -> None:
        udiff = _udiff_for("player.gd", OLD_TEXT, [Hunk(remove=["s15n"], insert=["S15N"])])
        result = check_blast_radius(udiff, root_cause_errors=[_root("res://player.gd", 15)], pointers=[])
        assert result.ok, result.violations

    def test_change_within_15_lines_passes(self) -> None:
        # 根因第 15 行，改第 1 行：hunk 覆盖 1–4，|1-15|=14 ≤ 15
        udiff = _udiff_for("player.gd", OLD_TEXT, [Hunk(remove=["s1n"], insert=["S1N"])])
        result = check_blast_radius(udiff, root_cause_errors=[_root("res://player.gd", 15)], pointers=[])
        assert result.ok, result.violations

    def test_change_beyond_15_lines_rejected(self) -> None:
        # 根因第 15 行，改第 30 行之前的更远位置：造一个 40 行文件
        text = "\n".join(f"s{i}n" for i in range(1, 41))
        udiff = _udiff_for("player.gd", text, [Hunk(remove=["s40n"], insert=["S40N"])])
        result = check_blast_radius(udiff, root_cause_errors=[_root("res://player.gd", 15)], pointers=[])
        assert not result.ok
        assert any(v.id == OUTSIDE_BLAST_RADIUS for v in result.violations)

    def test_file_not_in_c_rejected(self) -> None:
        udiff = _udiff_for("other.gd", OLD_TEXT, [Hunk(remove=["s15n"], insert=["S15N"])])
        result = check_blast_radius(udiff, root_cause_errors=[_root("res://player.gd", 15)], pointers=[])
        assert not result.ok
        assert result.violations[0].file == "res://other.gd"


class TestRootLineNone:
    """根因 line 为 None 时，不把该文件整份放行。"""

    def test_none_line_does_not_whitewash_file(self) -> None:
        udiff = _udiff_for("player.gd", OLD_TEXT, [Hunk(remove=["s15n"], insert=["S15N"])])
        result = check_blast_radius(udiff, root_cause_errors=[_root("res://player.gd", None)], pointers=[])
        assert not result.ok

    def test_none_line_but_in_scope_passes(self) -> None:
        # line 为 None 但文件在 declared_scope 里 → 整份放行
        udiff = _udiff_for("player.gd", OLD_TEXT, [Hunk(remove=["s15n"], insert=["S15N"])])
        result = check_blast_radius(
            udiff,
            root_cause_errors=[_root("res://player.gd", None)],
            pointers=[],
            declared_scope=["res://player.gd"],
        )
        assert result.ok, result.violations


class TestPointerTarget:
    """pointer 的目标文件任意行通过；其 res_path（引用方）不因此进入 C。"""

    def test_pointer_target_any_line_passes(self) -> None:
        udiff = _udiff_for("player.gd", OLD_TEXT, [Hunk(remove=["s1n"], insert=["S1N"])])
        result = check_blast_radius(
            udiff, root_cause_errors=[], pointers=[_pointer("res://player.gd")]
        )
        assert result.ok, result.violations

    def test_pointer_referrer_not_in_c(self) -> None:
        # pointer 的 res_path 是 referrer.gd，改 referrer.gd 不应被放行
        udiff = _udiff_for("referrer.gd", OLD_TEXT, [Hunk(remove=["s1n"], insert=["S1N"])])
        result = check_blast_radius(
            udiff, root_cause_errors=[], pointers=[_pointer("res://player.gd")]
        )
        assert not result.ok
        assert result.violations[0].file == "res://referrer.gd"


class TestDeclaredScope:
    """declared_scope 的文件路径让该文件整份进入 C；#func:名字 至少让该文件进入 C。"""

    def test_plain_path_scopes_whole_file(self) -> None:
        udiff = _udiff_for("player.gd", OLD_TEXT, [Hunk(remove=["s1n"], insert=["S1N"])])
        result = check_blast_radius(
            udiff, root_cause_errors=[], pointers=[], declared_scope=["res://player.gd"]
        )
        assert result.ok, result.violations

    def test_func_anchor_scopes_file(self) -> None:
        udiff = _udiff_for("player.gd", OLD_TEXT, [Hunk(remove=["s1n"], insert=["S1N"])])
        result = check_blast_radius(
            udiff,
            root_cause_errors=[],
            pointers=[],
            declared_scope=["res://player.gd#func:_ready"],
        )
        assert result.ok, result.violations



def _hunk():
    return Hunk(
        remove=["yield(get_tree(), 'idle_frame')"],
        insert=["await get_tree().process_frame"],
    )

class TestRuleIdExemption:
    """rule_id 在规则库存在时允许改该行 old_symbol 的出现位置；否则豁免不生效。"""

    def _make_rules_db(self, tmp_path: Path, table: str = "rules") -> Path:
        db = tmp_path / "rules.db"
        conn = sqlite3.connect(db)
        conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, old_symbol TEXT)")
        conn.execute(f"INSERT INTO {table} (id, old_symbol) VALUES (7, 'yield')")
        conn.commit()
        conn.close()
        return db

    def test_existing_rule_id_allows_symbol_line(self, tmp_path: Path) -> None:
        db = self._make_rules_db(tmp_path)
        # 根因第 15 行，改第 40 行（超出 15），但第 40 行含 old_symbol 'yield'
        text = "\n".join(f"s{i}n" for i in range(1, 40)) + "\nyield(get_tree(), 'idle_frame')"
        udiff = _udiff_for("player.gd", text, [_hunk()])
        result = check_blast_radius(
            udiff,
            root_cause_errors=[_root("res://player.gd", 15)],
            pointers=[],
            rule_id=7,
            rules_db_path=db,
            file_texts={"res://player.gd": text},
        )
        assert result.ok, result.violations

    def test_nonexistent_rule_id_no_exemption(self, tmp_path: Path) -> None:
        db = self._make_rules_db(tmp_path)
        text = "\n".join(f"s{i}n" for i in range(1, 40)) + "\nyield(get_tree(), 'idle_frame')"
        udiff = _udiff_for("player.gd", text, [_hunk()])
        result = check_blast_radius(
            udiff,
            root_cause_errors=[_root("res://player.gd", 15)],
            pointers=[],
            rule_id=999,
            rules_db_path=db,
            file_texts={"res://player.gd": text},
        )
        assert not result.ok

    def test_unopenable_db_no_exemption(self, tmp_path: Path) -> None:
        text = "\n".join(f"s{i}n" for i in range(1, 40)) + "\nyield(get_tree(), 'idle_frame')"
        udiff = _udiff_for("player.gd", text, [_hunk()])
        result = check_blast_radius(
            udiff,
            root_cause_errors=[_root("res://player.gd", 15)],
            pointers=[],
            rule_id=7,
            rules_db_path=tmp_path / "missing.db",
            file_texts={"res://player.gd": text},
        )
        assert not result.ok

    def test_migration_rules_table_name_accepted(self, tmp_path: Path) -> None:
        # 表名是 migration_rules 时也能查到
        db = self._make_rules_db(tmp_path, table="migration_rules")
        text = "\n".join(f"s{i}n" for i in range(1, 40)) + "\nyield(get_tree(), 'idle_frame')"
        udiff = _udiff_for("player.gd", text, [_hunk()])
        result = check_blast_radius(
            udiff,
            root_cause_errors=[_root("res://player.gd", 15)],
            pointers=[],
            rule_id=7,
            rules_db_path=db,
            file_texts={"res://player.gd": text},
        )
        assert result.ok, result.violations
