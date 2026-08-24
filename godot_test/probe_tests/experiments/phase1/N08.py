#!/usr/bin/env python3
"""N08 正式采集脚本：exit code 可信度、启动成功语义与 --debug 存活性。P1-2。

按 README.md P1-2 步骤表采集；交叉表与存活性判定交给 analyzer/exitcode.py。
本脚本只落盘，不下结论（不写 CONFIRMED / exit_code 可否当 success）。
假 Godot 禁止用于本实验。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROBE_ROOT = Path(__file__).resolve().parents[2]
if str(PROBE_ROOT) not in sys.path:
    sys.path.insert(0, str(PROBE_ROOT))

from experiments.util import probe  # noqa: E402
from experiments.util.probe import (  # noqa: E402
    ARTIFACTS_DIR,
    BlockedError,
    ProbeError,
    StaleError,
)

N = "N08"
FIXTURES = (
    "phase1/CleanControl",
    "phase1/NP-SYNTAX",
    "phase1/NP-AUTOLOAD",
    "phase1/NP-ADDON",
)
CRASH_MARK = "handle_crash: Program crashed with signal 11"


def main() -> int:
    os.environ.pop("PROBE_GODOT", None)

    try:
        run = probe.start(
            N,
            repeat_default=3,
            timeout_seconds=30,
            fixtures=FIXTURES,
            depends_on=("N09",),
        )
        if run.identity.fake:
            raise ProbeError(
                "BLOCKED: N08 正式采集禁止假 Godot。"
                f" 当前可执行文件是 {run.identity.path}"
            )

        # 1  V1  CleanControl 全项目哨兵  WARM  ×3
        with probe.workspace("phase1/CleanControl", group="clean-control") as ws:
            probe.warm(ws)
            run.measure(ws, group="clean-control", step="v1", cmd="V1", cache="WARM")

        # 2–8  NP-SYNTAX。按步骤表顺序，不按项目矩阵展开。
        with probe.workspace("phase1/NP-SYNTAX", group="np-syntax") as ws:
            probe.warm(ws)
            # 2  V2  orphan_bad_parse.gd  WARM  ×3
            run.measure(
                ws,
                group="np-syntax",
                step="v2",
                cmd="V2",
                cache="WARM",
                target="res://orphan_bad_parse.gd",
            )
            # 3  V1  全项目哨兵  WARM  ×3
            run.measure(ws, group="np-syntax", step="v1", cmd="V1", cache="WARM")
            # 4  V3  整个项目  COLD  ×3
            probe.cold(ws)
            run.measure(ws, group="np-syntax", step="v3", cmd="V3", cache="COLD")
            # 5  V4  整个项目  COLD  ×3
            probe.cold(ws)
            run.measure(ws, group="np-syntax", step="v4", cmd="V4", cache="COLD")
            # 6  V5  整个项目  WARM  ×3  （B9）
            probe.warm(ws)
            run.measure(ws, group="np-syntax", step="v5", cmd="V5", cache="WARM")
            # 7  V6  整个项目  WARM  ×3
            run.measure(ws, group="np-syntax", step="v6", cmd="V6", cache="WARM")
            # 8  V7  V1 + --verbose  WARM  ×3
            run.measure(ws, group="np-syntax", step="v7", cmd="V7", cache="WARM")

        # 9  V2  NP-AUTOLOAD uses_autoload.gd  COLD  ×3
        # 只采 rc；「有真错误＝否」由 N01 回填，本脚本不预判。
        with probe.workspace("phase1/NP-AUTOLOAD", group="np-autoload") as ws:
            probe.cold(ws)
            run.measure(
                ws,
                group="np-autoload",
                step="v2",
                cmd="V2",
                cache="COLD",
                target="res://uses_autoload.gd",
            )

        # 10  V8  独立工作区；timeout 30；repeat 1。
        v8_groups = ["np-syntax"]
        with probe.workspace("phase1/NP-SYNTAX", group="np-syntax") as ws:
            probe.warm(ws)
            recs = run.measure(
                ws,
                group="np-syntax",
                step="v8",
                cmd="V8",
                cache="WARM",
                target="res://orphan_bad_parse.gd",
                repeat=1,
                timeout_seconds=30,
            )
            dest = ARTIFACTS_DIR / recs[0]["dir"]
            _write_v8_extras(dest)
            reproduced = _v8_reproduced(dest)

        # 未复现才允许 NP-ADDON 补跑一次；两次都未复现则停，不再追加。
        if not reproduced:
            v8_groups.append("np-addon")
            with probe.workspace("phase1/NP-ADDON", group="np-addon") as ws:
                probe.warm(ws)
                recs = run.measure(
                    ws,
                    group="np-addon",
                    step="v8",
                    cmd="V8",
                    cache="WARM",
                    target="res://uses_addon.gd",
                    repeat=1,
                    timeout_seconds=30,
                )
                _write_v8_extras(ARTIFACTS_DIR / recs[0]["dir"])

        run.finish(
            exports={
                "kind": "collection-pointer",
                "repeat": 3,
                "groups": [
                    "clean-control",
                    "np-syntax",
                    "np-autoload",
                    *([g for g in v8_groups if g == "np-addon"]),
                ],
                "v8_groups": v8_groups,
            }
        )
    except (BlockedError, StaleError, ProbeError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return 0


def _write_v8_extras(dest: Path) -> None:
    """步骤 10 额外记录：残留 Godot 进程与 crash 标记（采集，不是判定）。"""
    leftover = _godot_engine_pids()
    stderr = ""
    stderr_path = dest / "stderr.log"
    if stderr_path.is_file():
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    payload = {
        "godot_pids_after_measure": leftover,
        "leftover_godot": bool(leftover),
        "crash_mark_in_stderr": CRASH_MARK in stderr,
    }
    dest.joinpath("leftover-procs.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _v8_reproduced(dest: Path) -> bool:
    """采集侧是否看到挂死 / signal 11 / crash 文案。只决定要不要补跑，不写结论。"""
    status_path = dest / "process-status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else {}
    stderr = ""
    stderr_path = dest / "stderr.log"
    if stderr_path.is_file():
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    if status.get("timed_out"):
        return True
    if status.get("rc") in (134, 139, -11):
        return True
    if status.get("signal") == 11:
        return True
    if CRASH_MARK in stderr:
        return True
    return False


def _godot_engine_pids() -> list[int]:
    try:
        out = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="], text=True)
    except (OSError, subprocess.CalledProcessError):
        return []
    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        pid_s, _, cmd = line.partition(" ")
        cmd_l = cmd.lower()
        if "python" in cmd_l:
            continue
        name = cmd.split()[0] if cmd else ""
        base = Path(name).name.lower()
        if base in {"godot", "godot4"} or "godot.app/contents/macos/godot" in cmd_l:
            try:
                pids.append(int(pid_s))
            except ValueError:
                continue
    return pids


if __name__ == "__main__":
    sys.exit(main())
