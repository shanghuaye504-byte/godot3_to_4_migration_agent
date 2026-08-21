"""Fake Godot：按脚本吐出预设 stdout/stderr/rc，并可模拟 hang 以便测 killpg。

用法：作为 EngineProfile.executable 的 argv 前缀，kernel 以 argv 列表启动，不经 shell。
假二进制不得被任何“已确认”结论引用。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

try:
    from . import scripts
except ImportError:  # python path/to/fake_godot.py （kernel 以 argv 列表启动）
    import scripts


def executable_argv() -> list:
    """返回可作为 EngineProfile.executable 的 argv 前缀。"""
    return [sys.executable, str(Path(__file__).resolve())]


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cwd = Path.cwd()
    response = scripts.lookup(argv, cwd=cwd)
    sleep_seconds = float(os.environ.get("FAKE_GODOT_SLEEP", response.get("sleep") or 0))
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)
    sys.stdout.write(response.get("stdout") or "")
    sys.stderr.write(response.get("stderr") or "")
    sys.stdout.flush()
    sys.stderr.flush()
    return int(response.get("returncode") or 0)


if __name__ == "__main__":
    sys.exit(main())
