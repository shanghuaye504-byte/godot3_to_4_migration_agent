"""工作区路径解析：res:// 与相对路径 → 绝对路径，带安全约束。

约束见 inline_tools/ARCHITECTURE.md 第 2 节。
"""

from __future__ import annotations

import os
from pathlib import Path

# 禁止进入的目录名：导入缓存、引擎产物、索引状态，都不是源码
FORBIDDEN_PARTS = frozenset({".godot", ".import", ".codeindex"})

# 稳定错误码，与 read/grep ARCHITECTURE.md 对齐
PATH_ESCAPE = "PATH_ESCAPE"
PATH_FORBIDDEN = "PATH_FORBIDDEN"


class WorkspaceError(Exception):
    """路径解析失败。code 是稳定的错误码字符串，供结构化错误返回。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def resolve_project_root(project_root: str | os.PathLike[str]) -> Path:
    """规范化 project_root：展开 ~，取绝对路径，realpath。"""
    raw = Path(project_root).expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    return Path(os.path.realpath(raw))


def resolve_workspace_path(
    project_root: str | os.PathLike[str],
    path: str | os.PathLike[str],
) -> tuple[Path, str]:
    """把模型给出的路径解析成绝对路径，同时返回 res:// 形式的规范相对路径。

    接受 ``res://...`` 或相对 project_root 的路径。去掉 res:// 后拼到
    project_root 下再 realpath；结果必须仍在工作区内，且任何路径分量
    不得命中 .godot / .import / .codeindex。

    返回 ``(absolute_path, res_relative)``，res_relative 形如 ``res://foo/bar.gd``。
    """
    root = resolve_project_root(project_root)

    raw = str(path)
    if raw.startswith("res://"):
        raw = raw[len("res://"):]

    candidate = Path(raw)
    if candidate.is_absolute():
        raise WorkspaceError(PATH_ESCAPE, f"absolute path not allowed: {path!r}")

    full = root / candidate
    resolved = Path(os.path.realpath(full))

    try:
        rel = resolved.relative_to(root)
    except ValueError as exc:
        raise WorkspaceError(
            PATH_ESCAPE, f"path escapes project root: {path!r}"
        ) from exc

    for part in rel.parts:
        if part in FORBIDDEN_PARTS:
            raise WorkspaceError(
                PATH_FORBIDDEN, f"path under forbidden directory: {path!r}"
            )

    res_rel = "res://" + "/".join(rel.parts)
    return resolved, res_rel
