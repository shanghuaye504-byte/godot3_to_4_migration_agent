"""Godot 进程启动与终止。

用 argv 列表启动（不经 shell）；独立进程组（start_new_session=True）；
timeout 时 killpg(SIGKILL)；记录 rc / signal / wall time。
"""

from __future__ import annotations

import signal as signal_module
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .types import ProcessStatus


def killpg_safe(pgid: int, sig: int = signal_module.SIGKILL) -> None:
    try:
        import os

        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass
    except PermissionError:
        pass


def find_residual_pids(pgid: int) -> list:
    result = subprocess.run(
        ["ps", "-A", "-o", "pid=,pgid="], capture_output=True, text=True, check=False
    )
    residual = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        pid_str, pgid_str = parts
        try:
            pid, line_pgid = int(pid_str), int(pgid_str)
        except ValueError:
            continue
        if line_pgid == pgid:
            residual.append(pid)
    return residual


def run(
    argv: list,
    *,
    cwd: Path,
    env: Optional[dict] = None,
    timeout_seconds: float,
) -> tuple:
    started_at = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    pgid = proc.pid
    timed_out = False
    try:
        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            killpg_safe(pgid, signal_module.SIGKILL)
            stdout_bytes, stderr_bytes = proc.communicate()
    finally:
        killpg_safe(pgid, signal_module.SIGKILL)

    ended_at = datetime.now(timezone.utc).isoformat()
    wall_time = time.monotonic() - start

    raw_rc = proc.returncode
    if raw_rc is not None and raw_rc < 0:
        returncode = None
        sig = -raw_rc
    else:
        returncode = raw_rc
        sig = None

    status = ProcessStatus(
        pid=proc.pid,
        pgid=pgid,
        returncode=returncode,
        signal=sig,
        timed_out=timed_out,
        wall_time_seconds=wall_time,
        started_at=started_at,
        ended_at=ended_at,
    )
    stdout_text = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
    stderr_text = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
    return status, stdout_text, stderr_text
