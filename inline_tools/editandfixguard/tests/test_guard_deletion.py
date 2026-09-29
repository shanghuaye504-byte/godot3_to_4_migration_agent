"""判据 3（删除比例，含 G4.1、G4.2）的验收测试。

验收条目见 NEXT_STEP.md「Step 5 判据 3」。测试直接调用
`inline_tools.editandfixguard.guard.check_deletion`，udiff 输入来自 Step 2
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
check_deletion = guard.check_deletion

FILE = "res://player.gd"


def _make_udiff(old_text: str, hunks: list) -> tuple[str, str]:
    """apply_hunks 产出 (udiff, new_text)。"""
    result = apply_hunks(old_text, hunks)
    assert result["ok"] is True, result
    return result["udiff"], result["new_text"]


class TestDeletionRatioWarn:
    """removed - added > 10 且 added < removed * 0.3 → warn，不 block。"""

    def test_ratio_warn_not_block(self) -> None:
        # 删 20 行加 2 行：20-2=18 > 10 且 2 < 20*0.3=6 → warn
        old_text = "\n".join(f"line {i}" for i in range(1, 31))
        remove = [f"line {i}" for i in range(1, 21)]
        udiff, new_text = _make_udiff(old_text, [Hunk(remove=remove, insert=["a", "b"])])
        result = check_deletion(udiff, file=FILE, old_text=old_text, new_text=new_text)
        ratio = [v for v in result.violations if v.id == guard.DELETION_RATIO]
        assert len(ratio) == 1
        assert ratio[0].block is False
        assert result.ok  # warn 不 block

    def test_balanced_edit_no_warn(self) -> None:
        # 删 5 行加 5 行：不触发
        old_text = "\n".join(f"line {i}" for i in range(1, 31))
        remove = [f"line {i}" for i in range(1, 6)]
        udiff, new_text = _make_udiff(old_text, [Hunk(remove=remove, insert=["a", "b", "c", "d", "e"])])
        result = check_deletion(udiff, file=FILE, old_text=old_text, new_text=new_text)
        assert not any(v.id == guard.DELETION_RATIO for v in result.violations)


class TestAddedRemovedCounting:
    """added / removed 不计 +++ 与 --- 行。"""

    def test_header_lines_not_counted(self) -> None:
        old_text = "\n".join(f"line {i}" for i in range(1, 11))
        udiff, _ = _make_udiff(old_text, [Hunk(remove=["line 5"], insert=["LINE 5"])])
        added, removed = guard._count_added_removed(udiff)
        assert added == 1
        assert removed == 1


class TestBulkDelete:
    """删除行数 > max(30, 文件行数的 40%) 且未设 allow_bulk_delete → BULK_DELETE。"""

    def test_over_30_lines_rejected(self) -> None:
        # 100 行文件删 35 行：35 > max(30, 40)=40？不，35 < 40。用 50 行。
        old_text = "\n".join(f"line {i}" for i in range(1, 51))
        remove = [f"line {i}" for i in range(1, 36)]  # 35 行 > max(30, 20)=30
        udiff, new_text = _make_udiff(old_text, [Hunk(remove=remove, insert=["x"])])
        result = check_deletion(udiff, file=FILE, old_text=old_text, new_text=new_text)
        assert not result.ok
        assert any(v.id == guard.BULK_DELETE and v.block for v in result.violations)

    def test_over_40_percent_rejected(self) -> None:
        # 200 行文件删 85 行：85 > max(30, 80)=80
        old_text = "\n".join(f"line {i}" for i in range(1, 201))
        remove = [f"line {i}" for i in range(1, 86)]
        udiff, new_text = _make_udiff(old_text, [Hunk(remove=remove, insert=["x"])])
        result = check_deletion(udiff, file=FILE, old_text=old_text, new_text=new_text)
        assert not result.ok
        assert any(v.id == guard.BULK_DELETE for v in result.violations)

    def test_under_threshold_passes(self) -> None:
        # 100 行文件删 39 行：39 < max(30, 40)=40
        old_text = "\n".join(f"line {i}" for i in range(1, 101))
        remove = [f"line {i}" for i in range(1, 40)]
        udiff, new_text = _make_udiff(old_text, [Hunk(remove=remove, insert=["x"])])
        result = check_deletion(udiff, file=FILE, old_text=old_text, new_text=new_text)
        assert not any(v.id == guard.BULK_DELETE for v in result.violations)


class TestAllowBulkDelete:
    """allow_bulk_delete=True 只豁免 G4.1，比值 warn 仍在，并记入 override。"""

    def test_exempts_g41_but_keeps_ratio_warn(self) -> None:
        # 100 行文件删 50 行加 5 行：G4.1 超阈值 + G4.2 比值 warn
        old_text = "\n".join(f"line {i}" for i in range(1, 101))
        remove = [f"line {i}" for i in range(1, 51)]
        udiff, new_text = _make_udiff(old_text, [Hunk(remove=remove, insert=["a", "b", "c", "d", "e"])])
        result = check_deletion(
            udiff, file=FILE, old_text=old_text, new_text=new_text, allow_bulk_delete=True
        )
        # G4.1 被豁免：没有 block 的 BULK_DELETE
        assert not any(v.id == guard.BULK_DELETE and v.block for v in result.violations)
        # 比值 warn 仍在
        assert any(v.id == guard.DELETION_RATIO and not v.block for v in result.violations)
        # 记入 override
        assert guard.BULK_DELETE in result.overrides
        assert result.ok  # 只剩 warn

    def test_exemption_recorded_in_overrides(self) -> None:
        old_text = "\n".join(f"line {i}" for i in range(1, 51))
        remove = [f"line {i}" for i in range(1, 36)]
        udiff, new_text = _make_udiff(old_text, [Hunk(remove=remove, insert=["x"])])
        result = check_deletion(
            udiff, file=FILE, old_text=old_text, new_text=new_text, allow_bulk_delete=True
        )
        assert guard.BULK_DELETE in result.overrides


class TestFileTruncated:
    """new_text 为空或字节数 < old_text 的 10% → FILE_TRUNCATED，无豁免。"""

    def test_empty_new_text_rejected(self) -> None:
        old_text = "\n".join(f"line {i}" for i in range(1, 51))
        # 删全部行：构造一个 remove 所有的 hunk
        remove = [f"line {i}" for i in range(1, 51)]
        result_anchor = apply_hunks(old_text, [Hunk(remove=remove, insert=[])])
        # apply_hunks 对全删会怎样？new_text 为空 → EMPTY_EDIT？不，全删不是 EMPTY_EDIT
        if result_anchor["ok"]:
            udiff, new_text = result_anchor["udiff"], result_anchor["new_text"]
        else:
            # 构造不出来就直接手拼 udiff
            udiff = "".join(f"-{line}\n" for line in remove)
            new_text = ""
        result = check_deletion(udiff, file=FILE, old_text=old_text, new_text=new_text)
        assert not result.ok
        assert any(v.id == guard.FILE_TRUNCATED for v in result.violations)

    def test_tiny_new_text_rejected(self) -> None:
        old_text = "x" * 1000
        new_text = "x" * 50  # 5% < 10%
        udiff = ""  # check_deletion 的截断判断不依赖 udiff 内容
        result = check_deletion(udiff, file=FILE, old_text=old_text, new_text=new_text)
        assert not result.ok
        assert any(v.id == guard.FILE_TRUNCATED for v in result.violations)

    def test_no_exemption_for_truncation(self) -> None:
        # allow_bulk_delete 不能豁免 FILE_TRUNCATED
        old_text = "x" * 1000
        new_text = ""
        result = check_deletion(
            "", file=FILE, old_text=old_text, new_text=new_text, allow_bulk_delete=True
        )
        assert not result.ok
        assert any(v.id == guard.FILE_TRUNCATED and v.block for v in result.violations)
        assert guard.FILE_TRUNCATED not in result.overrides
