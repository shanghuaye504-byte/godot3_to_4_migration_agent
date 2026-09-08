"""缓存不变量 —— 方案文档 §2.1.1 / §2.1.3。

WARM 的判据是 `.godot/global_script_class_cache.cfg` 存在，不是「有个 `.godot/` 目录」。
空 `.godot/` 仍算 COLD。本模块不删缓存、不跑 import。
"""

from __future__ import annotations

from pathlib import Path

CLASS_CACHE_REL = Path(".godot") / "global_script_class_cache.cfg"


def cache_is_warm(workspace: Path) -> bool:
    """工作区是否已经有可用的 class cache。"""
    return (Path(workspace) / CLASS_CACHE_REL).is_file()
