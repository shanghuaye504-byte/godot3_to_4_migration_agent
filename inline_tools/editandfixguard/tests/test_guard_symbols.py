"""判据 2（语法回归）、G2.1（符号消失）、G5.1（反向迁移）的验收测试。

验收条目见 NEXT_STEP.md「Step 4 判据 2、G2.1、G5.1」。测试直接调用
`inline_tools.editandfixguard.symbols.check_symbols`，不经过 edit()；
不调用 writer，不写 index.db。
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


symbols = _import("inline_tools.editandfixguard.symbols")
check_symbols = symbols.check_symbols

FILE = "res://player.gd"

BEFORE = """extends KinematicBody2D

var speed := 200
var hp := 10

func _ready():
	pass

func take_damage(amount):
	hp -= amount
"""


def _rules_db(tmp_path: Path, old_symbols: list[str]) -> Path:
    db = tmp_path / "rules.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE rules (id INTEGER PRIMARY KEY, old_symbol TEXT, symbol_kind TEXT)")
    for i, name in enumerate(old_symbols, start=1):
        conn.execute("INSERT INTO rules (id, old_symbol, symbol_kind) VALUES (?, ?, ?)", (i, name, "func"))
    conn.commit()
    conn.close()
    return db


class TestSyntaxRegression:
    """new 的 error 节点数大于 old → SYNTAX_REGRESSION，不报符号消失。"""

    def test_more_errors_rejected_without_symbol_report(self) -> None:
        new_text = BEFORE + "\nfunc broken(:\n"  # 语法残缺
        result = check_symbols(FILE, BEFORE, new_text)
        assert not result.ok
        ids = [v.id for v in result.violations]
        assert symbols.SYNTAX_REGRESSION in ids
        assert symbols.SYMBOL_REMOVED not in ids

    def test_fewer_errors_no_rejection(self) -> None:
        # old 本身有 error，new 修好了：new < old，不拒绝
        old_text = BEFORE + "\nfunc broken(:\n"
        result = check_symbols(FILE, old_text, BEFORE)
        assert result.ok, result.violations


class TestSymbolKinds:
    """kind 仅为 class/func/signal/var/const/enum；注释和字符串里的 func 不算符号。"""

    def test_all_six_kinds_tracked(self) -> None:
        old_text = """class_name Player

signal died

const MAX_HP := 100
var hp := 10

enum State {IDLE, RUN}

func _ready():
	pass
"""
        # 删掉 func：应报符号消失
        new_text = old_text.replace("func _ready():\n\tpass\n", "")
        result = check_symbols(FILE, old_text, new_text)
        assert any(v.symbol == "_ready" and v.id == symbols.SYMBOL_REMOVED for v in result.violations)

    def test_func_in_comment_not_a_symbol(self) -> None:
        old_text = BEFORE + "\n# func _fake(): 这行注释不算\n"
        new_text = BEFORE
        result = check_symbols(FILE, old_text, new_text)
        assert result.ok, result.violations

    def test_func_in_string_not_a_symbol(self) -> None:
        old_text = BEFORE + '\nvar hint := "func _fake():"\n'
        new_text = BEFORE
        result = check_symbols(FILE, old_text, new_text)
        # hint 变量消失会报，但 _fake 不会
        fake = [v for v in result.violations if v.symbol == "_fake"]
        assert not fake


class TestSymbolRemoved:
    """消失的符号未在 declared_scope 逐个列出 → 拒绝。"""

    def test_undeclared_removal_rejected(self) -> None:
        new_text = BEFORE.replace("func take_damage(amount):\n\thp -= amount\n", "")
        result = check_symbols(FILE, BEFORE, new_text)
        assert not result.ok
        assert any(v.symbol == "take_damage" for v in result.violations)

    def test_declared_removal_passes(self) -> None:
        new_text = BEFORE.replace("func take_damage(amount):\n\thp -= amount\n", "")
        result = check_symbols(
            FILE, BEFORE, new_text,
            declared_scope=["res://player.gd#func:take_damage"],
        )
        assert result.ok, result.violations

    def test_partial_declaration_still_rejected(self) -> None:
        # 同时删两个符号，只声明一个
        new_text = BEFORE.replace("func take_damage(amount):\n\thp -= amount\n", "").replace("var hp := 10\n", "")
        result = check_symbols(
            FILE, BEFORE, new_text,
            declared_scope=["res://player.gd#func:take_damage"],
        )
        assert not result.ok
        assert any(v.symbol == "hp" for v in result.violations)


class TestErrorCountGate:
    """new 的计数不大于 old 且两边并非都为 0 时，判据 2 和 G2.1 都不拒绝。"""

    def test_equal_nonzero_errors_no_rejection(self) -> None:
        # 两边各有一个 error 节点：不做符号差，不拒绝
        old_text = BEFORE + "\nfunc broken(:\n"
        new_text = BEFORE.replace("func take_damage(amount):\n\thp -= amount\n", "") + "\nfunc broken(:\n"
        result = check_symbols(FILE, old_text, new_text)
        assert result.ok, result.violations


class TestCreateSkipsCriterion2:
    """create 时 old_text 为空，判据 2 不触发。"""

    def test_empty_old_text_no_symbol_check(self) -> None:
        result = check_symbols(FILE, "", "func _ready():\n\tpass\n")
        assert result.ok, result.violations


class TestReverseMigration:
    """S_after − S_before 落在 old_symbol 列 → REVERSE_MIGRATION；旧文本已有的不算。"""

    def test_new_old_symbol_rejected(self, tmp_path: Path) -> None:
        # 新定义的符号名 instance 落在 old_symbol 列
        db = _rules_db(tmp_path, ["instance"])
        new_text = BEFORE + "\nfunc instance():\n\tpass\n"
        result = check_symbols(FILE, BEFORE, new_text, rules_db_path=db)
        assert not result.ok
        assert any(v.id == symbols.REVERSE_MIGRATION and v.symbol == "instance" for v in result.violations)

    def test_preexisting_old_symbol_not_flagged(self, tmp_path: Path) -> None:
        # old_text 里本来就有 instance 这个符号名，不是「新出现」
        db = _rules_db(tmp_path, ["helper"])
        old_text = BEFORE + "\nfunc helper():\n\tpass\n"
        new_text = old_text + "\nvar x := 1\n"
        result = check_symbols(FILE, old_text, new_text, rules_db_path=db)
        reverse = [v for v in result.violations if v.id == symbols.REVERSE_MIGRATION]
        assert not reverse

    def test_rules_db_unavailable_rejects(self, tmp_path: Path) -> None:
        new_text = BEFORE + "\nvar x := 1\n"
        result = check_symbols(FILE, BEFORE, new_text, rules_db_path=tmp_path / "missing.db")
        assert not result.ok
        assert any(v.id == symbols.RULES_DB_UNAVAILABLE for v in result.violations)

    def test_query_not_limited_to_class_kind(self, tmp_path: Path) -> None:
        # old_symbol 是 func kind，也应被查到（不限 symbol_kind='class'）
        db = _rules_db(tmp_path, ["yield_func"])
        new_text = BEFORE + "\nfunc yield_func():\n\tpass\n"
        result = check_symbols(FILE, BEFORE, new_text, rules_db_path=db)
        assert any(v.id == symbols.REVERSE_MIGRATION for v in result.violations)
