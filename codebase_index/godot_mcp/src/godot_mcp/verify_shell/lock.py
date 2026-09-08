"""工作区串行锁 —— 方案文档 §12 / 先验 N14。

同一 `project_root` 上两个 Godot verify 会互踩 `.godot/`。锁文件放在项目根
`.godot_mcp_verify.lock`，不放进 `.godot/`（COLD 时那个目录还不存在）。
"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

LOCK_FILENAME = ".godot_mcp_verify.lock"


class WorkspaceBusyError(RuntimeError):
    """非阻塞模式下锁已被占用。"""


@contextmanager
def workspace_lock(project_root: Path, *, blocking: bool = True) -> Iterator[None]:
    """持有工作区独占锁直到退出。`blocking=False` 且被占则抛 `WorkspaceBusyError`。"""
    root = Path(project_root)
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / LOCK_FILENAME
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    flags = fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        fcntl.flock(fd, flags)
    except BlockingIOError as exc:
        os.close(fd)
        raise WorkspaceBusyError(f"工作区已有 verify 在跑：{root}") from exc
    try:
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
