#!/usr/bin/env python3
"""N03 正式采集脚本：class_name 冷缓存假阳性与新增 class_name 的 import 触发。P1-3。

按 README.md P1-3 步骤表采集；T1–T6 同一份工作区、不可并行、不可重排。
late_class.gd / uses_late.gd 在 T3 之后写入临时工作区，不进 fixture、不进 util。
本脚本只落盘，不下结论（不写 CONFIRMED / import_trigger_policy 最终取值）。
假 Godot 禁止用于本实验。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

PROBE_ROOT = Path(__file__).resolve().parents[2]
if str(PROBE_ROOT) not in sys.path:
    sys.path.insert(0, str(PROBE_ROOT))

from experiments.util import probe  # noqa: E402
from experiments.util.probe import (  # noqa: E402
    ARTIFACTS_DIR,
    WARM_MARKER,
    BlockedError,
    ProbeError,
    StaleError,
)

N = "N03"
FIXTURES = ("phase1/NP-GLOBALCLASS",)
GROUP = "np-globalclass"
CLASS_CACHE_REL = Path(".godot") / "global_script_class_cache.cfg"

LATE_CLASS = """class_name ProbeLate
extends Node

static func answer() -> int:
	return 7
"""

USES_LATE = """extends Node

func f() -> int:
	return ProbeLate.answer()
"""


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
                "BLOCKED: N03 正式采集禁止假 Godot。"
                f" 当前可执行文件是 {run.identity.path}"
            )

        with probe.workspace("phase1/NP-GLOBALCLASS", group=GROUP) as ws:
            # T1  V2  uses_class.gd  COLD  ×3
            recs = run.measure(
                ws,
                group=GROUP,
                step="t1",
                cmd="V2",
                cache="COLD",
                target="res://uses_class.gd",
            )
            _snapshot_class_cache(ws, recs)

            # T2  V3  整个项目  COLD  ×1  （COLD→WARM，不参与判定）
            recs = run.measure(
                ws,
                group=GROUP,
                step="t2",
                cmd="V3",
                cache="COLD",
                repeat=1,
            )
            _snapshot_class_cache(ws, recs)
            _mark_warm(ws, recs[0])

            # T3  V2  uses_class.gd  WARM  ×3
            recs = run.measure(
                ws,
                group=GROUP,
                step="t3",
                cmd="V2",
                cache="WARM",
                target="res://uses_class.gd",
            )
            _snapshot_class_cache(ws, recs)

            _write_late_files(ws)

            # T4  V2  uses_late.gd  PRESERVE  ×3
            recs = run.measure(
                ws,
                group=GROUP,
                step="t4",
                cmd="V2",
                cache="PRESERVE",
                target="res://uses_late.gd",
            )
            _snapshot_class_cache(ws, recs)

            # T5  V3  整个项目  PRESERVE  ×1  （PRESERVE→WARM）
            recs = run.measure(
                ws,
                group=GROUP,
                step="t5",
                cmd="V3",
                cache="PRESERVE",
                repeat=1,
            )
            _snapshot_class_cache(ws, recs)

            # T6  V2  uses_late.gd  WARM  ×3
            recs = run.measure(
                ws,
                group=GROUP,
                step="t6",
                cmd="V2",
                cache="WARM",
                target="res://uses_late.gd",
            )
            _snapshot_class_cache(ws, recs)

        run.finish(
            exports={
                "kind": "collection-pointer",
                "repeat": 3,
                "groups": [GROUP],
                "steps": ["t1", "t2", "t3", "t4", "t5", "t6"],
            }
        )
    except (BlockedError, StaleError, ProbeError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return 0


def _write_late_files(ws: probe.Workspace) -> None:
    """T3 之后在临时工作区生成 late 文件；不 import、不进 fixture。"""
    (ws.path / "late_class.gd").write_text(LATE_CLASS, encoding="utf-8")
    (ws.path / "uses_late.gd").write_text(USES_LATE, encoding="utf-8")


def _mark_warm(ws: probe.Workspace, rec: dict) -> None:
    """T2 的 V3 已建好缓存；写 marker，避免 T3 的 WARM 再跑一次 import。"""
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


def _snapshot_class_cache(ws: probe.Workspace, recs: list[dict]) -> None:
    """每步拷贝 global_script_class_cache.cfg 的内容与 hash（N03 私事）。"""
    src = ws.path / CLASS_CACHE_REL
    for rec in recs:
        dest = ARTIFACTS_DIR / rec["dir"]
        dest.mkdir(parents=True, exist_ok=True)
        if src.is_file():
            shutil.copy2(src, dest / "global_script_class_cache.cfg")
            digest = hashlib.sha256(src.read_bytes()).hexdigest()
            meta = {
                "exists": True,
                "sha256": digest,
                "bytes": src.stat().st_size,
                "workspace_rel": CLASS_CACHE_REL.as_posix(),
            }
        else:
            (dest / "missing.json").write_text(
                json.dumps(
                    {
                        "exists": False,
                        "workspace_rel": CLASS_CACHE_REL.as_posix(),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            meta = {
                "exists": False,
                "sha256": None,
                "bytes": 0,
                "workspace_rel": CLASS_CACHE_REL.as_posix(),
            }
        (dest / "class-cache-meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    sys.exit(main())
