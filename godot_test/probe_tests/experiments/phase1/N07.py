#!/usr/bin/env python3
"""N07 正式采集脚本：shader verifier 盲区（漏报，不是假阳性）。P1-9。

按 README.md P1-9 采集。全程一个 NP-SHADER 工作区。不跑 V8。
注入 np-warn-debug.ini，stdout 与 stderr 都看。不写回 fixture。
无 derived / GUI。默认哨兵只 preload *.gd，本实验不改 sentinel 默认 include。

本脚本只落盘，不下结论（不写 CONFIRMED / shader_coverage 最终取值）。
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

N = "N07"
FIXTURES = ("phase1/NP-SHADER",)
FRAGMENT = "np-warn-debug.ini"
GROUP = "np-shader"


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
                "BLOCKED: N07 正式采集禁止假 Godot。"
                f" 当前可执行文件是 {run.identity.path}"
            )

        with probe.workspace("phase1/NP-SHADER", group=GROUP) as ws:
            probe.settings(ws, FRAGMENT)

            # 1  V2  shader_user.gd  COLD  ×3
            #    脚本解析：preload 能否把 shader 错误抬到 GDScript 解析期。
            run.measure(
                ws,
                group=GROUP,
                step="s1",
                cmd="V2",
                cache="COLD",
                target="res://shader_user.gd",
            )

            # 2  V3  整个项目  COLD  ×3
            recs = run.measure(
                ws,
                group=GROUP,
                step="s2",
                cmd="V3",
                cache="COLD",
            )
            _mark_warm(ws, recs[-1])

            # 3  V2  shader_user.gd  WARM  ×3
            run.measure(
                ws,
                group=GROUP,
                step="s3",
                cmd="V2",
                cache="WARM",
                target="res://shader_user.gd",
            )

            # 4  V5  整个项目  WARM  ×3
            #    场景启动：main.tscn 上同时挂着坏/好材质。
            run.measure(
                ws,
                group=GROUP,
                step="s4",
                cmd="V5",
                cache="WARM",
            )

            # 5  V1  全项目哨兵  WARM  ×3
            #    默认 include 只有 *.gd，不传 include。
            run.measure(
                ws,
                group=GROUP,
                step="s5",
                cmd="V1",
                cache="WARM",
            )

        run.finish(
            exports={
                "kind": "collection-pointer",
                "repeat": 3,
                "groups": [GROUP],
                "steps": ["s1", "s2", "s3", "s4", "s5"],
                "fragment": FRAGMENT,
                "sentinel_include_default": [".gd"],
                "sentinel_extended": False,
                "signal_source": {
                    "s1": "script-parse-preload-cold",
                    "s2": "resource-import",
                    "s3": "script-parse-preload-warm",
                    "s4": "scene-run",
                    "s5": "sentinel-gd-only",
                },
                "script_order_note": (
                    "s2 结束后 _mark_warm，避免 s3 再偷跑 V3；"
                    "未改 sentinel 默认 include；"
                    "对照靠同一次日志里的 bad.gdshader vs good.gdshader；"
                    "V5 的 NP_SHADER_MAIN_STARTED 不能证明 shader 正确"
                ),
            }
        )
    except (BlockedError, StaleError, ProbeError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return 0


def _mark_warm(ws: probe.Workspace, rec: dict) -> None:
    """s2 的最后一次 V3 已建好缓存；写 marker，避免后续 WARM 再跑一次 import。"""
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
