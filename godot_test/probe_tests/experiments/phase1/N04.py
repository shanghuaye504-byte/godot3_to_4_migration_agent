#!/usr/bin/env python3
"""N04 正式采集脚本：级联错误淹没根因。P1-6。

按 README.md P1-6 采集；卡片步骤 1 原计划复用 N09 的 NP-CASCADE V3/V1，
本脚本改为在本 run 重跑，不读 N09 原始日志。不改 README 步骤表编号。

两个工作区：np-syntax（scene_bad 分母）、np-cascade（V3/V1/dep_1/leaf）。
分母必须是 scene_bad.gd，禁止 orphan_bad_parse.gd；dep_2–dep_5 不跑。

本脚本只落盘，不下结论（不写 CONFIRMED / 放大倍数 / root_cause_errors）。
假 Godot 禁止用于本实验。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROBE_ROOT = Path(__file__).resolve().parents[2]
if str(PROBE_ROOT) not in sys.path:
    sys.path.insert(0, str(PROBE_ROOT))

from experiments.util import probe  # noqa: E402
from experiments.util.probe import (  # noqa: E402
    WARM_MARKER,
    BlockedError,
    ProbeError,
    StaleError,
)

N = "N04"
FIXTURES = ("phase1/NP-SYNTAX", "phase1/NP-CASCADE")
GROUP_SYNTAX = "np-syntax"
GROUP_CASCADE = "np-cascade"


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
                "BLOCKED: N04 正式采集禁止假 Godot。"
                f" 当前可执行文件是 {run.identity.path}"
            )

        # 3  V2  scene_bad.gd  WARM  ×3
        #    卡片步骤 2。同构单根分母，不得用 orphan_bad_parse.gd。
        with probe.workspace("phase1/NP-SYNTAX", group=GROUP_SYNTAX) as ws:
            run.measure(
                ws,
                group=GROUP_SYNTAX,
                step="s3",
                cmd="V2",
                cache="WARM",
                target="res://scene_bad.gd",
            )

        with probe.workspace("phase1/NP-CASCADE", group=GROUP_CASCADE) as ws:
            # 1  V3  整个项目  COLD  ×3
            #    卡片步骤 1 的 V3，本 run 重跑，不复用 N09。
            recs = run.measure(
                ws,
                group=GROUP_CASCADE,
                step="s1",
                cmd="V3",
                cache="COLD",
            )
            _mark_warm(ws, recs[-1])

            # 2  V1  全项目哨兵  WARM  ×3
            #    卡片步骤 1 的 V1。人读时扣 __probe_ 人造级联边。
            run.measure(
                ws,
                group=GROUP_CASCADE,
                step="s2",
                cmd="V1",
                cache="WARM",
            )

            # 4  V2  dep_1.gd  WARM  ×3
            #    卡片步骤 3。直接 preload 根因：报根因还是症状。
            run.measure(
                ws,
                group=GROUP_CASCADE,
                step="s4",
                cmd="V2",
                cache="WARM",
                target="res://dep_1.gd",
            )

            # 5  V2  leaf.gd  WARM  ×3
            #    卡片步骤 4。二级依赖：传递性有多远。
            run.measure(
                ws,
                group=GROUP_CASCADE,
                step="s5",
                cmd="V2",
                cache="WARM",
                target="res://leaf.gd",
            )

        run.finish(
            exports={
                "kind": "collection-pointer",
                "repeat": 3,
                "groups": [GROUP_SYNTAX, GROUP_CASCADE],
                "steps": ["s1", "s2", "s3", "s4", "s5"],
                "script_order_note": (
                    "s1/s2=本 run 重跑 NP-CASCADE V3 COLD 与 V1 WARM，"
                    "不读 N09 的 np-cascade/v3 与 v1；"
                    "s3=scene_bad 分母；s4=dep_1；s5=leaf"
                ),
            }
        )
    except (BlockedError, StaleError, ProbeError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return 0


def _mark_warm(ws: probe.Workspace, rec: dict) -> None:
    """s1 的 V3 已建好缓存；写 marker，避免后续 WARM 再跑一次 import。"""
    godot = ws.path / ".godot"
    godot.mkdir(parents=True, exist_ok=True)
    marker = ws.path / WARM_MARKER
    marker.write_text(
        json.dumps(
            {
                "ok": True,
                "from_step": rec.get("step_id"),
                "rc": rec.get("rc"),
                "wall_time": rec.get("wall_time"),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    ws.warmed = True


if __name__ == "__main__":
    sys.exit(main())
