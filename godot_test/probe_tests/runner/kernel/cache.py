"""COLD / WARM / PRESERVE 缓存协议。

COLD 步骤前删除工作区 .godot/；WARM 步骤前确认 V3 import 已成功
（由 runner.py 在 V3 成功后调用 mark_warm）；PRESERVE 保留当前 cache。
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .types import CacheState


class CacheStateError(Exception):
    pass


def _godot_dir(workspace: Path) -> Path:
    return Path(workspace) / ".godot"


def _warm_marker(workspace: Path) -> Path:
    return _godot_dir(workspace) / ".probe-warm-ok.json"


def ensure_cold(workspace: Path) -> None:
    godot_dir = _godot_dir(workspace)
    if godot_dir.exists():
        shutil.rmtree(godot_dir)


def mark_warm(workspace: Path, step_id: str) -> None:
    godot_dir = _godot_dir(workspace)
    godot_dir.mkdir(parents=True, exist_ok=True)
    marker = _warm_marker(workspace)
    marker.write_text(
        json.dumps(
            {"step_id": step_id, "marked_at": datetime.now(timezone.utc).isoformat()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def is_warm(workspace: Path) -> bool:
    return _godot_dir(workspace).exists() and _warm_marker(workspace).exists()


def ensure_warm(workspace: Path) -> None:
    if not is_warm(workspace):
        raise CacheStateError("WARM 步骤要求之前有一次成功的 V3，但未找到 warm 标记")


def resolve_cache_state(cache_state: CacheState, workspace: Path) -> None:
    if cache_state == CacheState.COLD:
        ensure_cold(workspace)
    elif cache_state == CacheState.WARM:
        ensure_warm(workspace)
    elif cache_state == CacheState.PRESERVE:
        pass
    else:
        raise CacheStateError(f"未知 cache_state: {cache_state}")
