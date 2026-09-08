"""工作区锁：非阻塞抢锁失败。"""

from __future__ import annotations

from pathlib import Path

import pytest

from godot_mcp.verify_shell.lock import WorkspaceBusyError, workspace_lock


def test_nonblocking_second_lock_fails(tmp_path: Path) -> None:
    with workspace_lock(tmp_path, blocking=True):
        with pytest.raises(WorkspaceBusyError):
            with workspace_lock(tmp_path, blocking=False):
                pass


def test_lock_releases(tmp_path: Path) -> None:
    with workspace_lock(tmp_path):
        pass
    with workspace_lock(tmp_path, blocking=False):
        pass
