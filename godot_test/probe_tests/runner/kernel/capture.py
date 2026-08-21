"""一次测量的「快门」：只负责拍一条，不负责决定拍哪一条。

分工（务必和 runner 对照着看）：

  runner     决定：哪个 workspace、哪条 argv、是否 hook、重复第几次
  process    只启动/杀死进程，返回 rc 和 stdout/stderr
  workspace  提供 git diff（相对 clone 时的基线）
  capture    唯一把「跑前快照 + 启进程 + 跑后快照 + diff」焊成 RawResult 的地方

本模块不知道 YAML，不知道 group/step 顺序，不知道要不要 mark_warm。
step_id、Measurement、inputs_digest 都是 runner 填好后传进来的。

时间线（run_measurement）：
  1. snapshot_fs(ws)          跑前文件树
  2. process.run(argv)        真正的 Godot / Fake Godot
  3. snapshot_fs(ws)          跑后文件树
  4. git_diff_since_baseline  相对工作区初始 commit，不是 1 与 3 的差
  5. 打包成 RawResult 返回    不写磁盘（写盘是 artifacts.py）
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import process, workspace
from .types import FsEntry, FsSnapshot, Measurement, RawResult

_SKIP_DIR_NAMES = {".git"}


def snapshot_fs(ws: Path) -> FsSnapshot:
    ws = Path(ws)
    entries = []
    for path in sorted(ws.rglob("*")):
        if any(part in _SKIP_DIR_NAMES for part in path.relative_to(ws).parts):
            continue
        if not path.is_file():
            continue
        stat = path.stat()
        sha1 = hashlib.sha1(path.read_bytes()).hexdigest()
        entries.append(
            FsEntry(
                rel_path=path.relative_to(ws).as_posix(),
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                sha1=sha1,
                is_dir=False,
            )
        )
    return FsSnapshot(taken_at=datetime.now(timezone.utc).isoformat(), entries=tuple(entries))


def run_measurement(
    argv: list,
    *,
    ws: Path,
    timeout_seconds: float,
    env: Optional[dict],
    measurement: Measurement,
    step_id: str,
    hooks_applied: list,
    inputs_digest: str,
) -> RawResult:
    """按快门一次，返回一张 RawResult。调用方必须是 runner。

    入参里「标签」与「现场」分开：
      measurement / step_id / inputs_digest / hooks_applied
          —— runner 已经填好的场记，本函数原样写入 RawResult
      argv / ws / timeout / env
          —— 这次进程实际使用的现场

    不在这里：拼 V1 argv、COLD 删 .godot、落 stdout.log、finally 删 workspace。
    """
    fs_before = snapshot_fs(ws)
    status, stdout_text, stderr_text = process.run(argv, cwd=ws, env=env, timeout_seconds=timeout_seconds)
    fs_after = snapshot_fs(ws)
    diff_text = workspace.git_diff_since_baseline(ws)

    return RawResult(
        measurement=measurement,
        step_id=step_id,
        argv=list(argv),
        cwd=str(ws),
        env_overrides=dict(env or {}),
        stdout=stdout_text,
        stderr=stderr_text,
        process=status,
        fs_before=fs_before,
        fs_after=fs_after,
        workspace_diff=diff_text,
        hooks_applied=list(hooks_applied),
        inputs_digest=inputs_digest,
    )
