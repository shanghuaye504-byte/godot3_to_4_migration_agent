"""工作区源码快照与 git 风 unified diff。

给触发表用，不起 Godot。不把快照写进 `.godot/`（V3 import 可能冲掉）。
"""

from __future__ import annotations

import difflib
from pathlib import Path

SKIP_DIRS = frozenset({".godot", ".git"})
SNAPSHOT_SUFFIXES = frozenset({".gd", ".gdshader", ".shader", ".tres", ".uid"})


def scan_workspace(project_root: Path) -> dict[str, str]:
    """扫描工作区相关后缀，返回 `相对路径 → 文本`。跳过 `.godot/` 与 `.git/`。"""
    root = Path(project_root)
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.suffix not in SNAPSHOT_SUFFIXES:
            continue
        out[rel.as_posix()] = path.read_text(encoding="utf-8", errors="replace")
    return out


def diff_snapshots(old: dict[str, str], new: dict[str, str]) -> str:
    """把两份快照拼成 git 风格 unified diff，供 `parse_unified_diff` 使用。"""
    chunks: list[str] = []
    for path in sorted(set(old) | set(new)):
        previous = old.get(path)
        current = new.get(path)
        if previous == current:
            continue
        chunks.append(_file_diff(path, previous, current))
    return "\n".join(chunks)


def _file_diff(path: str, old: str | None, new: str | None) -> str:
    header = [f"diff --git a/{path} b/{path}"]
    if old is None:
        header.append("new file mode 100644")
        from_file = "/dev/null"
        to_file = f"b/{path}"
        old_lines: list[str] = []
        new_lines = _lines(new or "")
    elif new is None:
        header.append("deleted file mode 100644")
        from_file = f"a/{path}"
        to_file = "/dev/null"
        old_lines = _lines(old)
        new_lines = []
    else:
        from_file = f"a/{path}"
        to_file = f"b/{path}"
        old_lines = _lines(old)
        new_lines = _lines(new)

    body = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=from_file,
            tofile=to_file,
            lineterm="\n",
        )
    )
    lines = header + [line.rstrip("\n") for line in body]
    return "\n".join(lines)


def _lines(text: str) -> list[str]:
    if not text:
        return []
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    return lines
