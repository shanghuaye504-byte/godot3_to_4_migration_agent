"""锚定、内存替换、规范 unified diff（流水线第 1–4 步）。

行为依据 NEXT_STEP.md「Step 2 锚定与规范 diff」与「不许自行解释的约定」。
本步不写盘、不调用 git apply：所有替换都发生在内存文本上，输出 diff 文本。

不用 `godot_mcp.verify_shell.diff.DiffView` 取行号；行号一律 1-based，
由 difflib 与本模块自己算。
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any

# 稳定错误码
CONTEXT_TOO_LONG = "CONTEXT_TOO_LONG"
AMBIGUOUS_ANCHOR = "AMBIGUOUS_ANCHOR"
ANCHOR_NOT_FOUND = "ANCHOR_NOT_FOUND"
OVERLAPPING_HUNKS = "OVERLAPPING_HUNKS"
EMPTY_EDIT = "EMPTY_EDIT"

# warning 码（不拒绝，进入返回值 warnings）
FUZZY_ANCHOR = "FUZZY_ANCHOR"

# 「不许自行解释的约定」：context_before / context_after 各 0～3 行
MAX_CONTEXT_LINES = 3

# 模糊锚定阈值：SequenceMatcher ratio 严格大于它才接受
FUZZY_RATIO_THRESHOLD = 0.92

# ANCHOR_NOT_FOUND 时附上的最相似片段个数
TOP_CANDIDATES = 3


@dataclass
class Hunk:
    """一次锚定替换。context_before / context_after 各 0～3 行。"""

    context_before: list[str] = field(default_factory=list)
    remove: list[str] = field(default_factory=list)
    insert: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    error.update(extra)
    return {"ok": False, "error": error}


def _all_match_lines(haystack: str, needle: list[str]) -> list[int]:
    """needle 在 haystack 里全部命中位置的 1-based 起始行号。"""
    needle_str = "\n".join(needle)
    if not needle_str:
        return []
    lines: list[int] = []
    start = 0
    while True:
        idx = haystack.find(needle_str, start)
        if idx < 0:
            break
        lines.append(haystack.count("\n", 0, idx) + 1)
        start = idx + 1
    return lines


def _ratio(haystack_lines: list[str], start: int, size: int, needle: list[str]) -> float:
    """needle 与 haystack 第 start 行起 size 行的 SequenceMatcher ratio。"""
    window = "\n".join(haystack_lines[start - 1 : start - 1 + size])
    return difflib.SequenceMatcher(None, "\n".join(needle), window).ratio()


def _fuzzy_candidates(
    haystack_lines: list[str], needle: list[str]
) -> list[tuple[int, float]]:
    """所有与 needle 等长窗口的 (1-based 起始行, ratio)，按 ratio 降序。"""
    size = len(needle)
    if size == 0 or len(haystack_lines) < size:
        return []
    scored = [
        (start, _ratio(haystack_lines, start, size, needle))
        for start in range(1, len(haystack_lines) - size + 2)
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


def _locate(
    haystack: str, haystack_lines: list[str], hunk: Hunk
) -> tuple[tuple[int, int] | None, dict[str, Any] | None, list[str]]:
    """定位一个 hunk。返回 (行区间, 拒绝 dict, warnings)。

    行区间为 1-based [start, end]（含端点），覆盖 context_before + remove +
    context_after 整段；拒绝时行区间为 None。
    """
    needle = hunk.context_before + hunk.remove + hunk.context_after
    if not needle:
        return None, _error(ANCHOR_NOT_FOUND, "hunk has empty needle"), []

    # 1. 精确匹配
    matches = _all_match_lines(haystack, needle)
    if len(matches) > 1:
        return None, _error(
            AMBIGUOUS_ANCHOR,
            f"needle matched {len(matches)} times",
            candidate_lines=matches,
        ), []
    if len(matches) == 1:
        return (matches[0], matches[0] + len(needle) - 1), None, []

    # 2. 归一化匹配：行尾空白、tab/space（CRLF→LF 由按行表示隐含）。
    #    归一化是双向的：needle 与文件行都归一到同一形式再比，否则
    #    「文件用 tab、needle 用空格」永远匹配不上。
    norm_haystack = "\n".join(line.rstrip().expandtabs(4) for line in haystack_lines)
    norm_needle = [line.rstrip().expandtabs(4) for line in needle]
    matches = _all_match_lines(norm_haystack, norm_needle)
    if len(matches) > 1:
        return None, _error(
            AMBIGUOUS_ANCHOR,
            f"needle matched {len(matches)} times after normalization",
            candidate_lines=matches,
        ), []
    if len(matches) == 1:
        return (matches[0], matches[0] + len(needle) - 1), None, []
    # 3. 模糊匹配：ratio > 0.92 接受并带 FUZZY_ANCHOR；否则附最相似的 3 个片段
    candidates = _fuzzy_candidates(haystack_lines, needle)
    if candidates and candidates[0][1] > FUZZY_RATIO_THRESHOLD:
        start, ratio = candidates[0]
        warnings = [f"{FUZZY_ANCHOR}: line {start} ratio {ratio:.3f}"]
        return (start, start + len(needle) - 1), None, warnings

    snippets = [
        {
            "line": start,
            "ratio": round(ratio, 3),
            "snippet": haystack_lines[start - 1 : start - 1 + len(needle)],
        }
        for start, ratio in candidates[:TOP_CANDIDATES]
    ]
    return None, _error(
        ANCHOR_NOT_FOUND, "anchor not found", candidates=snippets
    ), []


def apply_hunks(old_text: str, hunks: list[Hunk]) -> dict[str, Any]:
    """在内存里把 hunks 应用到 old_text，产出 new_text 与规范 unified diff。

    成功返回 ``{"ok": True, "new_text", "udiff", "warnings"}``；失败返回
    ``{"ok": False, "error": {...}}``。任何分支都不写盘。
    """
    if not hunks:
        return _error(EMPTY_EDIT, "no hunks given")

    for hunk in hunks:
        if len(hunk.context_before) > MAX_CONTEXT_LINES:
            return _error(
                CONTEXT_TOO_LONG,
                f"context_before has {len(hunk.context_before)} lines, max {MAX_CONTEXT_LINES}",
            )
        if len(hunk.context_after) > MAX_CONTEXT_LINES:
            return _error(
                CONTEXT_TOO_LONG,
                f"context_after has {len(hunk.context_after)} lines, max {MAX_CONTEXT_LINES}",
            )

    old_lines = old_text.splitlines()

    # 1. 逐个锚定
    located: list[tuple[Hunk, int, int]] = []
    warnings: list[str] = []
    for hunk in hunks:
        line_range, rejection, hunk_warnings = _locate(old_text, old_lines, hunk)
        if rejection is not None:
            return rejection
        warnings.extend(hunk_warnings)
        assert line_range is not None
        located.append((hunk, line_range[0], line_range[1]))

    # 2. hunk 行区间交叠 → OVERLAPPING_HUNKS
    ordered = sorted(located, key=lambda item: item[1])
    for prev, curr in zip(ordered, ordered[1:]):
        if curr[1] <= prev[2]:
            return _error(
                OVERLAPPING_HUNKS,
                f"hunk at line {curr[1]} overlaps hunk at line {prev[1]}",
            )

    # 3. 从后往前替换，避免行号漂移
    new_lines = list(old_lines)
    for hunk, start, end in sorted(located, key=lambda item: item[1], reverse=True):
        replacement = hunk.context_before + hunk.insert + hunk.context_after
        new_lines[start - 1 : end] = replacement
    new_text = "\n".join(new_lines)
    # splitlines 丢了尾部换行；old_text 以换行结尾时 new_text 也得以换行结尾，
    # 否则落盘字节与 git 的行模型对不上
    if old_text.endswith("\n") and not new_text.endswith("\n"):
        new_text += "\n"

    # 4. 字节相同 → EMPTY_EDIT
    if new_text == old_text:
        return _error(EMPTY_EDIT, "new_text is identical to old_text")

    # 5. 规范 unified diff：n=3，hunk 头 1-based
    trailing_newline = old_text.endswith("\n")
    udiff = "".join(
        difflib.unified_diff(
            [line + "\n" for line in old_lines],
            [line + "\n" for line in new_lines],
            fromfile="a/file",
            tofile="b/file",
            n=3,
        )
    )
    # 文件以换行结尾时，最后一行 context/增删后的 "\n" 是行内换行不是额外空行；
    # difflib 此时产出的 udiff 与 git 行模型一致，无需调整。无尾部换行时
    # difflib 也不会加 `\ No newline` 标记，本步不处理这种文件的 git apply。
    return {"ok": True, "new_text": new_text, "udiff": udiff, "warnings": warnings}
