"""入队拒收 —— 方案文档 §12 / 先验 N13。

C# / GDExtension 仓库不在本 verifier 支持边界内。只扫项目文件，跳过 `.godot/`。
"""

from __future__ import annotations

from pathlib import Path

UNSUPPORTED_SUFFIXES = (".csproj", ".gdextension")
_SKIP_DIRS = {".godot", ".git"}


class UnsupportedProjectError(ValueError):
    """项目含不支持的工程类型，应在入队/本轮开始时硬拒。"""


def find_unsupported_files(project_root: Path) -> list[Path]:
    """返回项目里所有 `.csproj` / `.gdextension`（相对路径已 resolve）。"""
    root = Path(project_root)
    hits: list[Path] = []
    if not root.is_dir():
        return hits
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix in UNSUPPORTED_SUFFIXES:
            hits.append(path)
    return sorted(hits)


def reject_if_unsupported(project_root: Path) -> None:
    """发现不支持的文件则抛 `UnsupportedProjectError`。"""
    hits = find_unsupported_files(project_root)
    if not hits:
        return
    shown = ", ".join(p.relative_to(project_root).as_posix() for p in hits[:8])
    extra = "" if len(hits) <= 8 else f" 等 {len(hits)} 个"
    raise UnsupportedProjectError(
        f"本 verifier 拒收 C#/GDExtension 项目：{shown}{extra}"
    )
