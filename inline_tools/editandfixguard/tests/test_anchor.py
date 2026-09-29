"""anchor（流水线第 1–4 步：锚定、内存替换、规范 diff）的验收测试。

验收条目见 NEXT_STEP.md「Step 2 锚定与规范 diff」。测试直接调用
`inline_tools.editandfixguard.anchor`，不经过尚未实现的 edit()；本步不写盘。
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _import_anchor():
    sys.path.insert(0, str(REPO_ROOT))
    try:
        return importlib.import_module("inline_tools.editandfixguard.anchor")
    finally:
        sys.path.remove(str(REPO_ROOT))


anchor = _import_anchor()
Hunk = anchor.Hunk
apply_hunks = anchor.apply_hunks

OLD_TEXT = "\n".join(
    [
        "extends KinematicBody2D",   # 1
        "",                          # 2
        "var speed := 200",          # 3
        "",                          # 4
        "func _ready():",            # 5
        "\tvelocity = Vector2.ZERO",  # 6
        "\tprint(speed)",            # 7
        "",                          # 8
        "func _process(delta):",     # 9
        "\tpass",                    # 10
    ]
)


class TestUniqueAnchor:
    """needle = context_before + remove + context_after；命中 1 次得到 1-based 行号。"""

    def test_unique_match_replaces_remove_lines(self) -> None:
        hunk = Hunk(
            context_before=["var speed := 200", ""],
            remove=["func _ready():"],
            insert=["func _enter_tree():"],
            context_after=["\tvelocity = Vector2.ZERO"],
        )
        result = apply_hunks(OLD_TEXT, [hunk])
        assert result["ok"] is True
        new_lines = result["new_text"].split("\n")
        assert new_lines[4] == "func _enter_tree():"  # 原第 5 行被替换
        assert new_lines[2] == "var speed := 200"     # context 不动
        assert new_lines[5] == "\tvelocity = Vector2.ZERO"

    def test_remove_only_needle(self) -> None:
        hunk = Hunk(remove=["\tpass"], insert=["\tmove_and_slide()"])
        result = apply_hunks(OLD_TEXT, [hunk])
        assert result["ok"] is True
        assert result["new_text"].split("\n")[9] == "\tmove_and_slide()"


class TestAmbiguousAnchor:
    """命中多于 1 次 → AMBIGUOUS_ANCHOR，附全部候选行号。"""

    def test_multiple_matches_rejected_with_all_lines(self) -> None:
        text = "x = 1\ny = 2\nx = 1\ny = 3\nx = 1"
        result = apply_hunks(text, [Hunk(remove=["x = 1"], insert=["x = 2"])])
        assert result["ok"] is False
        assert result["error"]["code"] == "AMBIGUOUS_ANCHOR"
        assert result["error"]["candidate_lines"] == [1, 3, 5]


class TestNormalization:
    """精确失败后做行尾空白、CRLF→LF、tab/space 归一化。"""

    def test_trailing_whitespace_normalized(self) -> None:
        text = "func _ready():\n\tpass   \n"
        hunk = Hunk(remove=["\tpass"], insert=["\trun()"])
        result = apply_hunks(text, [hunk])
        assert result["ok"] is True
        assert "\trun()" in result["new_text"]

    def test_tab_space_normalized(self) -> None:
        # 文件用 tab，needle 用空格（4 空格 == 1 tab）
        hunk = Hunk(remove=["    velocity = Vector2.ZERO"], insert=["\tvelocity = Vector2.ONE"])
        result = apply_hunks(OLD_TEXT, [hunk])
        assert result["ok"] is True
        assert result["new_text"].split("\n")[5] == "\tvelocity = Vector2.ONE"

    def test_crlf_file_anchors_with_lf_needle(self) -> None:
        # CRLF 文件按行拆分后行内无 \r；needle 用 \n 连接即等价 CRLF→LF 归一化
        text = "func a():\r\n\tpass\r\n"
        hunk = Hunk(remove=["\tpass"], insert=["\trun()"])
        result = apply_hunks(text, [hunk])
        assert result["ok"] is True
        assert "\trun()" in result["new_text"]


class TestContextTooLong:
    """context_before 或 context_after 超过 3 行 → CONTEXT_TOO_LONG。"""

    def test_context_before_over_3(self) -> None:
        hunk = Hunk(context_before=["a", "b", "c", "d"], remove=["x"], insert=["y"])
        result = apply_hunks(OLD_TEXT, [hunk])
        assert result["error"]["code"] == "CONTEXT_TOO_LONG"

    def test_context_after_over_3(self) -> None:
        hunk = Hunk(remove=["x"], insert=["y"], context_after=["a", "b", "c", "d"])
        result = apply_hunks(OLD_TEXT, [hunk])
        assert result["error"]["code"] == "CONTEXT_TOO_LONG"

    def test_exactly_3_lines_allowed(self) -> None:
        hunk = Hunk(
            context_before=["", "var speed := 200", ""],
            remove=["func _ready():"],
            insert=["func _enter_tree():"],
        )
        assert apply_hunks(OLD_TEXT, [hunk])["ok"] is True


class TestFuzzyAnchor:
    """ratio > 0.92 接受并带 FUZZY_ANCHOR（不拒绝）；否则 ANCHOR_NOT_FOUND 附 3 个片段。"""

    def test_high_ratio_accepted_with_warning(self) -> None:
        # needle 与原文第 5–7 行只差一个字符串，ratio > 0.92
        hunk = Hunk(
            remove=["func _ready():", "\tvelocity = Vector2.ZERO", "\tprint(speed)"],
            insert=["func _ready():", "\tvelocity = Vector2.ONE", "\tprint(speed)"],
        )
        text = OLD_TEXT.replace("\tvelocity = Vector2.ZERO", "\tvelocity = Vector2.ZERO ")
        # 让精确与归一化都失败：needle 里 print 行与文件不同
        hunk.remove[2] = "\tprint(speed + 1)"
        result = apply_hunks(text, [hunk])
        assert result["ok"] is True
        assert any(w.startswith("FUZZY_ANCHOR") for w in result["warnings"])

    def test_low_ratio_rejected_with_top3_snippets(self) -> None:
        hunk = Hunk(remove=["def totally_unknown_function():", "\tnothing here", "\tat all"])
        result = apply_hunks(OLD_TEXT, [hunk])
        assert result["ok"] is False
        assert result["error"]["code"] == "ANCHOR_NOT_FOUND"
        candidates = result["error"]["candidates"]
        assert len(candidates) == 3
        # 附真实 1-based 行号，且按相似度降序
        assert all(c["line"] >= 1 for c in candidates)
        assert [c["ratio"] for c in candidates] == sorted(
            [c["ratio"] for c in candidates], reverse=True
        )
        assert all(isinstance(c["snippet"], list) for c in candidates)


class TestOverlappingHunks:
    """多个 hunk 行区间交叠 → OVERLAPPING_HUNKS。"""

    def test_overlapping_ranges_rejected(self) -> None:
        first = Hunk(
            context_before=["var speed := 200"],
            remove=[""],
            insert=["# blank"],
            context_after=["func _ready():"],
        )
        second = Hunk(remove=["func _ready():"], insert=["func _enter_tree():"])
        result = apply_hunks(OLD_TEXT, [first, second])
        assert result["error"]["code"] == "OVERLAPPING_HUNKS"

    def test_adjacent_ranges_allowed(self) -> None:
        first = Hunk(remove=["var speed := 200"], insert=["var speed := 300"])
        second = Hunk(remove=["\tpass"], insert=["\tmove_and_slide()"])
        result = apply_hunks(OLD_TEXT, [first, second])
        assert result["ok"] is True


class TestBackToFrontReplacement:
    """替换从后往前，避免行号漂移。"""

    def test_multiple_hunks_land_on_original_line_numbers(self) -> None:
        # 前一个 hunk 增加行数；若从前往后替换，后一个 hunk 会落错行
        first = Hunk(remove=["var speed := 200"], insert=["var speed := 300", "var hp := 10"])
        second = Hunk(remove=["\tpass"], insert=["\tmove_and_slide()"])
        result = apply_hunks(OLD_TEXT, [first, second])
        assert result["ok"] is True
        new_lines = result["new_text"].split("\n")
        assert new_lines[2] == "var speed := 300"
        assert new_lines[3] == "var hp := 10"
        # 原第 10 行 \tpass 现在应被替换，且只在那一处
        assert "\tmove_and_slide()" in new_lines
        assert "\tpass" not in new_lines
        assert new_lines[-1] == "\tmove_and_slide()"


class TestEmptyEdit:
    """new_text 与 old_text 字节相同 → EMPTY_EDIT。"""

    def test_identical_replacement_rejected(self) -> None:
        hunk = Hunk(remove=["var speed := 200"], insert=["var speed := 200"])
        result = apply_hunks(OLD_TEXT, [hunk])
        assert result["error"]["code"] == "EMPTY_EDIT"

    def test_no_hunks_rejected(self) -> None:
        assert apply_hunks(OLD_TEXT, [])["error"]["code"] == "EMPTY_EDIT"


class TestUnifiedDiffFormat:
    """difflib.unified_diff(..., n=3) 的 hunk 头是 1-based。"""

    def test_hunk_header_is_one_based(self) -> None:
        # 替换第 10 行：n=3 时旧文件从第 7 行开始，共 4 行
        hunk = Hunk(remove=["\tpass"], insert=["\tmove_and_slide()"])
        result = apply_hunks(OLD_TEXT, [hunk])
        assert result["ok"] is True
        header = re.search(r"^@@ -\d+(,\d+)? \+\d+(,\d+)? @@", result["udiff"], re.M)
        assert header is not None
        assert header.group(0) == "@@ -7,4 +7,4 @@"

    def test_diff_applies_back_to_new_text(self) -> None:
        # diff 内容与 new_text 自洽：+ 行去掉前导 + 后能在 new_text 里找到
        hunk = Hunk(remove=["var speed := 200"], insert=["var speed := 300"])
        result = apply_hunks(OLD_TEXT, [hunk])
        added = [
            line[1:] for line in result["udiff"].splitlines()
            if line.startswith("+") and not line.startswith("+++")
        ]
        assert added == ["var speed := 300"]
        assert "var speed := 300" in result["new_text"]


class TestNoDiskWrite:
    """本步不写盘：apply_hunks 是纯函数，不触碰文件系统。"""

    def test_pure_function_no_path_argument(self, tmp_path: Path) -> None:
        before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
        apply_hunks(OLD_TEXT, [Hunk(remove=["\tpass"], insert=["\trun()"])])
        after = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
        assert before == after
