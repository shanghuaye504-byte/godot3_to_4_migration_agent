"""`verify/runner.py`：不依赖本机 godot4 的子进程语义测试。

覆盖要点：
- kind 不在白名单 → KeyError
- 假二进制正常退出：timed_out=False，exit_code 原样，stdout/stderr 被收集
- 假二进制被 signal 杀：exit_code=None（CRASH 语义）
- 超时：timed_out=True、exit_code=None，且进程组（含 fork 出的子进程）被杀干净
- V1 无论正常退出还是超时，工作区都不再留下 __probe_sentinel.gd
"""

from __future__ import annotations

import os
import stat
import sys
import time
import uuid
from pathlib import Path

import pytest

from godot_mcp.verify.sentinel import SENTINEL_FILENAME
from godot_mcp.verify.runner import run_verify

_SHEBANG = "#!/usr/bin/env python3\n"


def _write_executable(path: Path, body: str) -> Path:
    path.write_text(_SHEBANG + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_unknown_kind_raises_keyerror(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        run_verify("not_a_kind", None, sys.executable, tmp_path)


def test_v2_requires_target(tmp_path: Path) -> None:
    fake = _write_executable(tmp_path / "fake_godot", "import sys; sys.exit(0)\n")
    with pytest.raises(ValueError):
        run_verify("V2", None, str(fake), tmp_path)


def test_normal_exit_collects_streams(tmp_path: Path) -> None:
    fake = _write_executable(
        tmp_path / "fake_godot",
        "import sys\n"
        "sys.stdout.write('STDOUT_OK\\n')\n"
        "sys.stderr.write('STDERR_INFO\\n')\n"
        "sys.exit(0)\n",
    )
    result = run_verify("V1", None, str(fake), tmp_path, timeout_s=10)
    assert result.kind == "V1"
    assert result.timed_out is False
    assert result.exit_code == 0
    assert "STDOUT_OK" in result.stdout
    assert "STDERR_INFO" in result.stderr
    assert not (tmp_path / SENTINEL_FILENAME).exists()


def test_nonzero_exit_is_not_timeout(tmp_path: Path) -> None:
    fake = _write_executable(
        tmp_path / "fake_godot",
        "import sys\n"
        "sys.stderr.write('SCRIPT ERROR: Parse Error\\n')\n"
        "sys.exit(1)\n",
    )
    result = run_verify("V2", "res://player.gd", str(fake), tmp_path, timeout_s=10)
    assert result.kind == "V2"
    assert result.timed_out is False
    assert result.exit_code == 1
    assert "Parse Error" in result.stderr


def test_signal_crash_sets_exit_code_none(tmp_path: Path) -> None:
    fake = _write_executable(
        tmp_path / "fake_godot",
        "import os, signal\n"
        "os.kill(os.getpid(), signal.SIGSEGV)\n",
    )
    result = run_verify("V1", None, str(fake), tmp_path, timeout_s=10)
    assert result.kind == "V1"
    assert result.timed_out is False
    assert result.exit_code is None
    assert not (tmp_path / SENTINEL_FILENAME).exists()


@pytest.mark.timeout(20)
def test_timeout_kills_process_group_and_removes_sentinel(tmp_path: Path) -> None:
    """假二进制 fork 一个子进程后无限睡；超时后父、子都应消失，哨兵也必须被删。"""
    token = uuid.uuid4().hex
    pid_file = tmp_path / f"pids-{token}.txt"
    fake = _write_executable(
        tmp_path / f"fake_godot_hang_{token}",
        "import os, time, pathlib, sys\n"
        f"pid_file = {str(pid_file)!r}\n"
        "child = os.fork()\n"
        "if child == 0:\n"
        "    time.sleep(120)\n"
        "    os._exit(0)\n"
        "pathlib.Path(pid_file).write_text(f'{os.getpid()}\\n{child}\\n')\n"
        "time.sleep(120)\n",
    )

    result = run_verify("V1", None, str(fake), tmp_path, timeout_s=1)

    assert result.kind == "V1"
    assert result.timed_out is True
    assert result.exit_code is None
    assert not (tmp_path / SENTINEL_FILENAME).exists()

    assert pid_file.exists(), "假二进制没有在超时前写出 pid 文件"
    pids = [int(line) for line in pid_file.read_text().splitlines() if line.strip()]
    time.sleep(0.2)
    still_alive = [pid for pid in pids if _is_alive(pid)]
    assert still_alive == [], f"残留进程: {still_alive}"


def test_v1_writes_sentinel_during_run(tmp_path: Path) -> None:
    """V1 运行期间哨兵必须存在，结束后必须消失。"""
    seen = tmp_path / "seen_sentinel.txt"
    fake = _write_executable(
        tmp_path / "fake_godot",
        "import pathlib, sys\n"
        f"seen = pathlib.Path({str(seen)!r})\n"
        f"sentinel = pathlib.Path({str(tmp_path / SENTINEL_FILENAME)!r})\n"
        "seen.write_text('yes' if sentinel.is_file() else 'no')\n"
        "sys.exit(0)\n",
    )
    (tmp_path / "player.gd").write_text("extends Node\n", encoding="utf-8")
    result = run_verify("V1", None, str(fake), tmp_path, timeout_s=10)
    assert result.exit_code == 0
    assert seen.read_text() == "yes"
    assert not (tmp_path / SENTINEL_FILENAME).exists()
