"""入队 UID 规范化 —— 方案文档 §2.1.4（N06）。

单独篡改的 `.uid` 在 V1/V2/V3 上全静默。入队时在隔离工作区删掉 sidecar，
再由外壳跑一次 V3 重建。禁止对用户原仓做 `git rm`——本函数只 `unlink` 工作区文件。
"""

from __future__ import annotations

from pathlib import Path

_SKIP_DIRS = {".godot", ".git"}


def list_uid_sidecars(project_root: Path) -> list[Path]:
    root = Path(project_root)
    hits: list[Path] = []
    if not root.is_dir():
        return hits
    for path in root.rglob("*.uid"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        hits.append(path)
    return sorted(hits)


def wipe_uid_sidecars(project_root: Path) -> list[Path]:
    """删除工作区内全部 `.uid` sidecar（跳过 `.godot/`），返回已删路径。"""
    removed: list[Path] = []
    for path in list_uid_sidecars(project_root):
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        removed.append(path)
    return removed
