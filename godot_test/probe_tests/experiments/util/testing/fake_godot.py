#!/usr/bin/env python3
"""Fake Godot：给 util 干跑用的替身可执行文件。

不是实验结论源。ARCHITECTURE 要求干跑用 PROBE_GODOT 指向任意可执行文件，
假二进制产物不得被任何「已确认」结论引用。本文件就是那个可执行文件，
不是旧 runner/testing 那套按 argv 查表的桩框架。

用法（与真 Godot 相同的 argv 形状）::

    python experiments/util/testing/fake_godot.py \\
        --headless --path /tmp/ws --quit

    PROBE_GODOT=/abs/path/to/fake_godot.py

接受 V1–V8 / --version / --help 以及 N15 用到的 converter 开关，
一律忽略其语义：不读项目、不写文件、不挂死。
stdout / stderr 永远是下面的固定原文，退出码永远 0。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 固定原文。probe.start 采集身份时可从 stdout 刮到版本行；
# FAKE_GODOT 标记用来保证这些日志不会被当成真机结论。
FIXED_STDOUT = (
    "Godot Engine v0.0.0.fake.probe_tests.deadbeef\n"
    "FAKE_GODOT_STDOUT\n"
)
FIXED_STDERR = "FAKE_GODOT_STDERR\n"


def executable_argv() -> list[str]:
    """可作为 PROBE_GODOT / subprocess argv 前缀：用当前解释器跑本文件。"""
    return [sys.executable, str(Path(__file__).resolve())]


def main(argv: list[str] | None = None) -> int:
    # 吞掉 Godot 风格参数，避免未知 flag 导致非 0。不根据 flag 改变输出。
    _ = list(sys.argv[1:] if argv is None else argv)
    sys.stdout.write(FIXED_STDOUT)
    sys.stderr.write(FIXED_STDERR)
    sys.stdout.flush()
    sys.stderr.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
