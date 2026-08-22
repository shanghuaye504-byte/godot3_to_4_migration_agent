#!/usr/bin/env python3
"""N09 正式采集脚本：非确定性与归一化。P1-1，第一阶段最先执行。

按 README.md P1-1 步骤表采集；步骤 9 的横向 diff 交给 analyzer/stability.py。
本脚本只落盘，不下结论（不写 CONFIRMED / signature-policy 字段规格）。
假 Godot 禁止用于本实验。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROBE_ROOT = Path(__file__).resolve().parents[2]
if str(PROBE_ROOT) not in sys.path:
    sys.path.insert(0, str(PROBE_ROOT))

from experiments.util import probe  # noqa: E402
from experiments.util.probe import BlockedError, ProbeError, StaleError  # noqa: E402

N = "N09"
FIXTURES = ("phase1/CleanControl", "phase1/NP-CASCADE")


def main() -> int:
    # 正式采集不得走 PROBE_GODOT 假二进制。
    os.environ.pop("PROBE_GODOT", None)

    try:
        run = probe.start(
            N,
            repeat_default=5,
            timeout_seconds=30,
            fixtures=FIXTURES,
        )
        if run.identity.fake:
            raise ProbeError(
                "BLOCKED: N09 正式采集禁止假 Godot。"
                f" 当前可执行文件是 {run.identity.path}"
            )

        # 步骤 1–5：CleanControl。group_id 进路径；与 np-cascade 会有同名 step_id。
        with probe.workspace("phase1/CleanControl", group="clean-control") as ws:
            # 1  V1  全项目哨兵  COLD  ×5
            probe.cold(ws)
            run.measure(ws, group="clean-control", step="v1", cmd="V1", cache="COLD")
            # 2  V1  全项目哨兵  WARM  ×5
            probe.warm(ws)
            run.measure(ws, group="clean-control", step="v1", cmd="V1", cache="WARM")
            # 3  V2  main.gd     WARM  ×5
            run.measure(
                ws,
                group="clean-control",
                step="v2",
                cmd="V2",
                cache="WARM",
                target="res://main.gd",
            )
            # 4  V3  整个项目    COLD  ×5
            probe.cold(ws)
            run.measure(ws, group="clean-control", step="v3", cmd="V3", cache="COLD")
            # 5  V5  整个项目    WARM  ×5
            probe.warm(ws)
            run.measure(ws, group="clean-control", step="v5", cmd="V5", cache="WARM")

        # 步骤 6–8：NP-CASCADE
        with probe.workspace("phase1/NP-CASCADE", group="np-cascade") as ws:
            # 6  V2  dep_1.gd    WARM  ×5
            probe.warm(ws)
            run.measure(
                ws,
                group="np-cascade",
                step="v2",
                cmd="V2",
                cache="WARM",
                target="res://dep_1.gd",
            )
            # 7  V3  整个项目    COLD  ×5
            probe.cold(ws)
            run.measure(ws, group="np-cascade", step="v3", cmd="V3", cache="COLD")
            # 8  V1  全项目哨兵  WARM  ×5
            probe.warm(ws)
            run.measure(ws, group="np-cascade", step="v1", cmd="V1", cache="WARM")

        # 步骤 9 不启动 Godot，不在本脚本里做横向 diff。
        run.finish(
            exports={
                "kind": "collection-pointer",
                "repeat": 5,
                "groups": ["clean-control", "np-cascade"],
                "np_cascade_logs": [
                    "np-cascade/v3/COLD",
                    "np-cascade/v1/WARM",
                ],
            }
        )
    except (BlockedError, StaleError, ProbeError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
