"""统一 finally 清理。

无论 timeout / crash / 异常 / 人工取消，都必须：杀进程组 -> 确认无残留 Godot ->
校验 workspace 内无 __probe_* 残留 -> 删除临时工作区 -> 校验 fixture 仍 clean。
由 runner.py 的 try/finally 无条件调用。
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Optional

from . import process, workspace


@dataclasses.dataclass
class CleanupReport:
    killed_pgids: list = dataclasses.field(default_factory=list)
    residual_pids: list = dataclasses.field(default_factory=list)
    probe_leftovers: list = dataclasses.field(default_factory=list)
    workspace_destroyed: bool = False
    fixture_verified: bool = True
    fixture_error: str = ""


def finally_cleanup(
    *,
    tracked_pgids: list,
    workspace_path: Optional[Path],
    workspaces_root: Path,
    fixture_dir: Optional[Path],
    fixture_expected_hash: Optional[str],
) -> CleanupReport:
    killed = []
    for pgid in tracked_pgids:
        process.killpg_safe(pgid)
        killed.append(pgid)

    residual = []
    for pgid in tracked_pgids:
        residual.extend(process.find_residual_pids(pgid))

    leftovers = []
    if workspace_path is not None and Path(workspace_path).exists():
        leftovers = [str(p) for p in workspace.find_probe_prefixed_leftovers(workspace_path)]

    fixture_verified = True
    fixture_error = ""
    if fixture_dir is not None and fixture_expected_hash is not None:
        try:
            workspace.verify_fixture_untouched(fixture_dir, fixture_expected_hash)
        except workspace.FixtureCorruptionError as exc:
            fixture_verified = False
            fixture_error = str(exc)

    workspace_destroyed = False
    if workspace_path is not None:
        workspace.destroy_workspace(workspace_path, workspaces_root)
        workspace_destroyed = not Path(workspace_path).exists()

    return CleanupReport(
        killed_pgids=killed,
        residual_pids=[str(p) for p in residual],
        probe_leftovers=leftovers,
        workspace_destroyed=workspace_destroyed,
        fixture_verified=fixture_verified,
        fixture_error=fixture_error,
    )
