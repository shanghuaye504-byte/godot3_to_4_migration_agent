#!/usr/bin/env python3
"""N05 正式采集脚本：warning 与 error 严重度混淆。P1-7。

按 README.md P1-7 采集。只跑 NP-WARN，不重跑 CleanControl（N09 已无 WARNING）。
不跑 V8。配置用 probe.settings 注入 np-warn-debug.ini，不写回 fixture。
NP-WARN 没有 plugin.cfg，不走 GUI / derived。

两个 group、两份工作区：default（步骤 1–3）与 warn-enabled（步骤 4–7）。
本脚本只落盘，不下结论（不写 CONFIRMED / enable_warnings 最终取值）。
假 Godot 禁止用于本实验。
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PROBE_ROOT = Path(__file__).resolve().parents[2]
if str(PROBE_ROOT) not in sys.path:
    sys.path.insert(0, str(PROBE_ROOT))

from experiments.util import probe  # noqa: E402
from experiments.util.probe import BlockedError, ProbeError, StaleError  # noqa: E402

N = "N05"
FIXTURES = ("phase1/NP-WARN",)
FRAGMENT = "np-warn-debug.ini"
GROUP_DEFAULT = "default"
GROUP_ON = "warn-enabled"


def main() -> int:
    os.environ.pop("PROBE_GODOT", None)

    try:
        run = probe.start(
            N,
            repeat_default=3,
            timeout_seconds=30,
            fixtures=FIXTURES,
            depends_on=("N09", "N08"),
        )
        if run.identity.fake:
            raise ProbeError(
                "BLOCKED: N05 正式采集禁止假 Godot。"
                f" 当前可执行文件是 {run.identity.path}"
            )

        with probe.workspace("phase1/NP-WARN", group=GROUP_DEFAULT) as ws:
            # 1  V2  warn.gd  WARM  ×3
            run.measure(
                ws,
                group=GROUP_DEFAULT,
                step="s1",
                cmd="V2",
                cache="WARM",
                target="res://warn.gd",
            )
            # 2  V1  全项目哨兵  WARM  ×3
            run.measure(
                ws,
                group=GROUP_DEFAULT,
                step="s2",
                cmd="V1",
                cache="WARM",
            )
            # 3  V3  整个项目  COLD  ×3
            run.measure(
                ws,
                group=GROUP_DEFAULT,
                step="s3",
                cmd="V3",
                cache="COLD",
            )

        with probe.workspace("phase1/NP-WARN", group=GROUP_ON) as ws:
            # 4  注入 warning 片段（只改临时工作区）
            probe.settings(ws, FRAGMENT)
            _snapshot_injected(ws, run)

            # 5  V2  warn.gd  WARM  ×3
            run.measure(
                ws,
                group=GROUP_ON,
                step="s5",
                cmd="V2",
                cache="WARM",
                target="res://warn.gd",
            )
            # 6  V1  全项目哨兵  WARM  ×3
            #    哨兵会 preload addons/noisy；exclude_addons 挡不住硬 preload。
            run.measure(
                ws,
                group=GROUP_ON,
                step="s6",
                cmd="V1",
                cache="WARM",
            )
            # 7  V3  整个项目  COLD  ×3
            #    exclude_addons 是否屏蔽 addon warning 的主观察面。
            run.measure(
                ws,
                group=GROUP_ON,
                step="s7",
                cmd="V3",
                cache="COLD",
            )

        run.finish(
            exports={
                "kind": "collection-pointer",
                "repeat": 3,
                "groups": [GROUP_DEFAULT, GROUP_ON],
                "steps": ["s1", "s2", "s3", "s4", "s5", "s6", "s7"],
                "fragment": FRAGMENT,
                "script_order_note": (
                    "s4=probe.settings(np-warn-debug.ini)，无 measure；"
                    "未跑 CleanControl，BG 用 N09 无 WARNING"
                ),
            }
        )
    except (BlockedError, StaleError, ProbeError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return 0


def _snapshot_injected(ws: probe.Workspace, run: probe.Run) -> None:
    """N05 私事：把注入后的 project.godot 拷到 artifacts，供人读片段原文。"""
    dest = run.artifact_root / GROUP_ON / "injected"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ws.path / "project.godot", dest / "project.godot")
    src = PROBE_ROOT / "experiments" / "common" / "fragments" / FRAGMENT
    shutil.copy2(src, dest / FRAGMENT)


if __name__ == "__main__":
    sys.exit(main())
