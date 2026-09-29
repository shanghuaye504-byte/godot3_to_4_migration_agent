"""判据 4（偷懒修复）的验收测试。

验收条目见 NEXT_STEP.md「Step 6 判据 4」。测试直接调用
`inline_tools.editandfixguard.guard.check_lazy_fix`，udiff 输入来自 Step 2
的 `apply_hunks`。不经过 edit()。
"""

from __future__ import annotations

import importlib
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
check_lazy_fix = guard.check_lazy_fix

FILE = "res://player.gd"


def _udiff(old_text: str, hunks: list) -> str:
    result = apply_hunks(old_text, hunks)
    assert result["ok"] is True, result
    return result["udiff"]


def _ids(result) -> list[str]:
    return [v.id for v in result.violations]


class TestBarePass:
    """整行 pass → block。"""

    def test_added_pass_is_block(self) -> None:
        old_text = "func _ready():\n\tvar x := 1\n"
        udiff = _udiff(old_text, [Hunk(remove=["\tvar x := 1"], insert=["\tpass"])])
        result = check_lazy_fix(udiff, file=FILE)
        assert not result.ok
        assert guard.LAZY_PASS in _ids(result)
        assert any(v.id == guard.LAZY_PASS and v.block for v in result.violations)

    def test_existing_pass_not_counted(self) -> None:
        # 文件里原有的 pass 不是 + 行，不算
        old_text = "func _ready():\n\tpass\nfunc _exit_tree():\n\tvar y := 2\n"
        udiff = _udiff(old_text, [Hunk(remove=["\tvar y := 2"], insert=["\tvar y := 3"])])
        result = check_lazy_fix(udiff, file=FILE)
        assert guard.LAZY_PASS not in _ids(result)


class TestTodoWarn:
    """# TODO / FIXME / XXX / HACK 与 # ... → warn。"""

    def test_todo_is_warn(self) -> None:
        old_text = "func _ready():\n\tvar x := 1\n"
        udiff = _udiff(old_text, [Hunk(remove=["\tvar x := 1"], insert=["\tvar x := 2  # TODO: tune"])])
        result = check_lazy_fix(udiff, file=FILE)
        assert guard.LAZY_TODO in _ids(result)
        assert any(v.id == guard.LAZY_TODO and not v.block for v in result.violations)
        assert result.ok  # warn 不 block

    def test_fixme_xxx_hack(self) -> None:
        for tag in ["FIXME", "XXX", "HACK"]:
            old_text = "func f():\n\tvar a := 1\n"
            udiff = _udiff(old_text, [Hunk(remove=["\tvar a := 1"], insert=[f"\tvar a := 2  # {tag}"])])
            result = check_lazy_fix(udiff, file=FILE)
            assert guard.LAZY_TODO in _ids(result), tag

    def test_ellipsis_comment_is_warn(self) -> None:
        old_text = "func f():\n\tvar a := 1\n"
        udiff = _udiff(old_text, [Hunk(remove=["\tvar a := 1"], insert=["\t# ..."])])
        result = check_lazy_fix(udiff, file=FILE)
        assert guard.LAZY_TODO in _ids(result)


class TestKeptOriginal:
    """注释含 original、unchanged、as before、其余、不变 → block。"""

    def test_original_is_block(self) -> None:
        old_text = "func f():\n\tvar a := 1\n"
        udiff = _udiff(old_text, [Hunk(remove=["\tvar a := 1"], insert=["\tvar a := 1  # keep original"])])
        result = check_lazy_fix(udiff, file=FILE)
        assert not result.ok
        assert guard.LAZY_KEPT_ORIGINAL in _ids(result)

    def test_unchanged_as_before(self) -> None:
        for word in ["unchanged", "as before"]:
            old_text = "func f():\n\tvar a := 1\n"
            udiff = _udiff(old_text, [Hunk(remove=["\tvar a := 1"], insert=[f"\tvar a := 2  # {word}"])])
            result = check_lazy_fix(udiff, file=FILE)
            assert guard.LAZY_KEPT_ORIGINAL in _ids(result), word

    def test_chinese_kept_original(self) -> None:
        for word in ["其余", "不变"]:
            old_text = "func f():\n\tvar a := 1\n"
            udiff = _udiff(old_text, [Hunk(remove=["\tvar a := 1"], insert=[f"\tvar a := 2  # {word}同上"])])
            result = check_lazy_fix(udiff, file=FILE)
            assert guard.LAZY_KEPT_ORIGINAL in _ids(result), word


class TestPushErrorNotImplemented:
    """push_error 引号内匹配 not implement → block。"""

    def test_push_error_not_implemented(self) -> None:
        old_text = "func f():\n\tvar a := 1\n"
        udiff = _udiff(old_text, [Hunk(remove=["\tvar a := 1"], insert=['\tpush_error("not implemented yet")'])])
        result = check_lazy_fix(udiff, file=FILE)
        assert not result.ok
        assert guard.LAZY_NOT_IMPLEMENTED in _ids(result)

    def test_push_error_other_message_ok(self) -> None:
        old_text = "func f():\n\tvar a := 1\n"
        udiff = _udiff(old_text, [Hunk(remove=["\tvar a := 1"], insert=['\tpush_error("invalid state")'])])
        result = check_lazy_fix(udiff, file=FILE)
        assert guard.LAZY_NOT_IMPLEMENTED not in _ids(result)


class TestCommentedOut:
    """- 行 strip 后等于 + 行去掉一个前导 # 再 strip → COMMENTED_OUT，block。"""

    def test_commented_out_is_block(self) -> None:
        old_text = "func f():\n\tvar a := 1\n"
        # 把 `\tvar a := 1` 改成 `\t# var a := 1`
        udiff = _udiff(old_text, [Hunk(remove=["\tvar a := 1"], insert=["\t# var a := 1"])])
        result = check_lazy_fix(udiff, file=FILE)
        assert not result.ok
        assert guard.COMMENTED_OUT in _ids(result)

    def test_real_change_not_commented_out(self) -> None:
        old_text = "func f():\n\tvar a := 1\n"
        udiff = _udiff(old_text, [Hunk(remove=["\tvar a := 1"], insert=["\tvar a := 2"])])
        result = check_lazy_fix(udiff, file=FILE)
        assert guard.COMMENTED_OUT not in _ids(result)


class TestNoOverride:
    """本判据没有 override。"""

    def test_no_overrides_recorded(self) -> None:
        old_text = "func f():\n\tvar a := 1\n"
        udiff = _udiff(old_text, [Hunk(remove=["\tvar a := 1"], insert=["\tpass"])])
        result = check_lazy_fix(udiff, file=FILE)
        assert result.overrides == []
