"""工作区源码快照与 git 风 unified diff。

给触发表用，不起 Godot。不把快照写进 `.godot/`（V3 import 可能冲掉）。

相关后缀全文进 RAM；过大则硬拒（`SnapshotTooLargeError`），不截断 diff。
"""

from __future__ import annotations

import difflib
from pathlib import Path

SKIP_DIRS = frozenset({".godot", ".git"})
SNAPSHOT_SUFFIXES = frozenset({".gd", ".gdshader", ".shader", ".tres", ".uid"})

# 目标：≤500 个相关后缀文件的仓一定能进。数字从宽，实测后再决断。
MAX_SNAPSHOT_FILES = 2000
MAX_SNAPSHOT_BYTES = 1024 * 1024 * 1024  # 1 GiB


class SnapshotTooLargeError(ValueError):
    """相关后缀全文快照超过文件数或字节硬上限，本轮开始失败、不半截 save。"""


def scan_workspace(
    project_root: Path,
    *,
    max_files: int | None = None,
    max_bytes: int | None = None,
) -> dict[str, str]:
    """扫描工作区相关后缀，返回 `相对路径 → 文本`。跳过 `.godot/` 与 `.git/`。

    边扫边用 `stat().st_size` 累加个数 / 字节；撞线立即抛，不先 `read_text`
    超限文件。上限默认读模块常量，便于测试 monkeypatch。
    """
    limit_files = MAX_SNAPSHOT_FILES if max_files is None else max_files
    limit_bytes = MAX_SNAPSHOT_BYTES if max_bytes is None else max_bytes
    root = Path(project_root)
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    file_count = 0
    byte_total = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.suffix not in SNAPSHOT_SUFFIXES:
            continue
        file_count += 1
        byte_total += path.stat().st_size
        if file_count > limit_files or byte_total > limit_bytes:
            raise SnapshotTooLargeError(
                "本 verifier 的内存快照不承接该仓："
                f"相关后缀文件 {file_count} 个 / {byte_total} 字节，"
                f"上限为 {limit_files} 个 / {limit_bytes} 字节。"
            )
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
