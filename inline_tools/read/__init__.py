"""read：按连续行区间读取工作区内的一个文本文件，返回带绝对行号的原文。

签名与边界见 read/ARCHITECTURE.md。
"""

from __future__ import annotations

import os
from typing import Any

from .._workspace import WorkspaceError, resolve_workspace_path

# 单次最多返回行数，见 read/ARCHITECTURE.md 第 2 节
MAX_LINES = 2000

# 稳定错误码
FILE_NOT_FOUND = "FILE_NOT_FOUND"
BAD_RANGE = "BAD_RANGE"


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


def read(
    project_root: str | os.PathLike[str],
    path: str,
    line_from: int = 1,
    line_to: int | None = None,
) -> dict[str, Any]:
    """读取工作区内一个文本文件的连续行区间。

    参数：
        project_root: 宿主注入的工作区根目录。
        path: ``res://...`` 或相对 project_root 的路径。
        line_from: 起始行，1-based，含本行。默认 1。
        line_to: 结束行，1-based，含本行。None 表示读到文件尾（受单次上限约束）。

    成功返回 ``{"ok": True, "path", "lines", "total_lines", "truncated"}``，
    失败返回 ``{"ok": False, "error": {"code", "message"}}``。
    """
    # 区间合法性先于路径解析：调用错误不伪装成空切片
    if line_from < 1:
        return _error(BAD_RANGE, f"line_from must be >= 1, got {line_from}")
    if line_to is not None and line_to < line_from:
        return _error(
            BAD_RANGE, f"line_to ({line_to}) must be >= line_from ({line_from})"
        )

    try:
        absolute, res_rel = resolve_workspace_path(project_root, path)
    except WorkspaceError as exc:
        return _error(exc.code, exc.message)

    if not absolute.exists() or not absolute.is_file():
        return _error(FILE_NOT_FOUND, f"file not found: {path!r}")

    # newline=None：Python 统一把 \\r\\n / \\r 转成 \\n；splitlines() 去掉行尾换行
    with open(absolute, encoding="utf-8", newline=None) as handle:
        all_lines = handle.read().splitlines()

    total_lines = len(all_lines)
    effective_to = total_lines if line_to is None else min(line_to, total_lines)

    selected = all_lines[line_from - 1 : effective_to]
    truncated = False
    if len(selected) > MAX_LINES:
        selected = selected[:MAX_LINES]
        truncated = True

    lines = [
        {"n": line_from + offset, "text": text}
        for offset, text in enumerate(selected)
    ]

    return {
        "ok": True,
        "path": res_rel,
        "lines": lines,
        "total_lines": total_lines,
        "truncated": truncated,
    }


__all__ = ["read", "MAX_LINES"]
