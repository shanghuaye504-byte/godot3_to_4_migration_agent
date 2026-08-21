"""一次测量的原始采集。

组合 fs_before -> process.run -> fs_after -> workspace diff，产出一次
Measurement 对应的 RawResult。是唯一把 process.py（纯进程）与
workspace.py（文件系统/diff）组合起来的地方。
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
