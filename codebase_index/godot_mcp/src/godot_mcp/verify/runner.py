"""校验子进程执行器：一次性 spawn → collect → exit（design.md 3.5）。

进程模型：一次性 Godot 子进程，跑完就收。

必须有的鲁棒性（CLAUDE.md 调研结论，刚性需求）：
- subprocess timeout：--check-only --debug 可能掉进交互 debugger 永久挂死
- 进程组 kill（start_new_session + killpg）：超时要把整个进程组杀掉，不能只杀父进程
- 区分"超时"与"失败"两种语义，返回结构里明确标出
"""

from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

from godot_mcp.verify.commands import VERIFY_COMMANDS
from godot_mcp.verify.sentinel import install_sentinel, remove_sentinel

DEFAULT_TIMEOUT_S = 120
_DRAIN_TIMEOUT_S = 5


@dataclass
class VerifyResult:
    """一次校验执行的原始结果（噪声过滤前的）。"""

    kind: str
    timed_out: bool
    exit_code: int | None
    stdout: str
    stderr: str


def run_verify(
    kind: str,
    target: str | None,
    godot_binary: str,
    project_root: Path,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> VerifyResult:
    """按 VERIFY_COMMANDS[kind] 拼命令行，起一次性子进程执行。

    kind 必须是 V1 / V2 / V3（不在白名单 → KeyError）。
    V1 会在 spawn 前写入 `__probe_sentinel.gd`，无论正常退出、超时还是崩溃，
    finally 里都删除，避免污染工作区。
    超时 → 杀整个进程组，返回 timed_out=True、exit_code=None。
    被 signal 杀死（非本函数触发的超时）→ timed_out=False、exit_code=None，
    调用方据此标 infra_status=CRASH。
    """
    project_root = Path(project_root)
    if kind == "V1":
        try:
            install_sentinel(project_root)
            return _spawn(kind, target, godot_binary, project_root, timeout_s)
        finally:
            remove_sentinel(project_root)
    return _spawn(kind, target, godot_binary, project_root, timeout_s)


def _spawn(
    kind: str,
    target: str | None,
    godot_binary: str,
    project_root: Path,
    timeout_s: int,
) -> VerifyResult:
    argv = [godot_binary, *VERIFY_COMMANDS[kind](target, project_root)]
    proc = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,  # Godot 及其派生子进程进入新进程组
        cwd=str(project_root),
        close_fds=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        stdout, stderr = _drain_output(proc)
        return VerifyResult(
            kind=kind,
            timed_out=True,
            exit_code=None,
            stdout=stdout,
            stderr=stderr,
        )

    return VerifyResult(
        kind=kind,
        timed_out=False,
        exit_code=_normalize_exit_code(proc.returncode),
        stdout=stdout or "",
        stderr=stderr or "",
    )


def _normalize_exit_code(returncode: int | None) -> int | None:
    """把 Popen.returncode 收成 VerifyResult.exit_code。

    None / 负值（被 signal 杀，例如 -11 = SIGSEGV）一律记成 None，
    好让调用方用「exit_code is None 且未超时」识别 CRASH。
    非负整数原样返回（含 Godot --check-only 不可靠的 0）。
    """
    if returncode is None or returncode < 0:
        return None
    return returncode


def _kill_process_group(proc: subprocess.Popen[str]) -> None:
    """杀掉 Godot 所在的整个进程组。

    必须先确认 pgid 不是当前进程组，避免 start_new_session 失败时误杀自己。
    进程已经消失时 swallow ProcessLookupError，再兜底 proc.kill()。
    """
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, OSError):
        _kill_proc_only(proc)
        return

    if pgid == os.getpgrp():
        # 安全阀：绝不向自己所在的进程组发 SIGKILL
        _kill_proc_only(proc)
        return

    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        _kill_proc_only(proc)


def _kill_proc_only(proc: subprocess.Popen[str]) -> None:
    try:
        proc.kill()
    except (ProcessLookupError, OSError):
        pass


def _drain_output(proc: subprocess.Popen[str]) -> tuple[str, str]:
    """杀完之后再 communicate 一次，避免僵尸 pipe；失败则空字符串兜底。"""
    try:
        stdout, stderr = proc.communicate(timeout=_DRAIN_TIMEOUT_S)
        return stdout or "", stderr or ""
    except subprocess.TimeoutExpired:
        _kill_proc_only(proc)
        return "", ""
