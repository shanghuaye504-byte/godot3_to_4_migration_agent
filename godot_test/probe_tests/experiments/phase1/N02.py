#!/usr/bin/env python3
"""N02 正式采集脚本：addon 单例假阳性（#111515）。P1-5。

按 README.md P1-5 采集。步骤 0 在同一份工作区只 apply 一次 derived
NP-ADDON@plugin-enabled；其后 s1–s4 都在「插件已启用」状态下跑。

本脚本只落盘，不下结论（不写 CONFIRMED / 白名单代码量裁决）。
假 Godot 禁止用于本实验。不跑 V8。对照用已落盘的 N01 NP-AUTOLOAD，本实验不重跑。

人读日志：
- ADD-USES：V2 是否 Identifier not found / not declared: DummySingleton
- ADD-MAIN：V5 是否打印 DUMMY_ALIVE / NP_ADDON_MAIN_OK
- 步骤 0 的 project.godot 是否含 [autoload] DummySingleton
"""

from __future__ import annotations

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
    BlockedError,
    ManualGateError,
    ProbeError,
    StaleError,
)

N = "N02"
FIXTURES = ("phase1/NP-ADDON",)
DERIVED = "NP-ADDON@plugin-enabled"
GROUP = "np-addon"
EXPECTED_UID = "uid://qmfp8cu17gl2"
SINGLETON_UID_REL = Path("addons") / "dummy" / "dummy_singleton.gd.uid"


def main() -> int:
    os.environ.pop("PROBE_GODOT", None)

    try:
        run = probe.start(
            N,
            repeat_default=3,
            timeout_seconds=30,
            fixtures=FIXTURES,
            derived=(DERIVED,),
            depends_on=("N01",),
        )
        if run.identity.fake:
            raise ProbeError(
                "BLOCKED: N02 正式采集禁止假 Godot。"
                f" 当前可执行文件是 {run.identity.path}"
            )

        with probe.workspace("phase1/NP-ADDON", group=GROUP) as ws:
            _assert_fixture_plugin_disabled(ws)

            # 0  apply_derived 一次。后续全部步骤共用这份已启用插件的工作区。
            probe.apply_derived(ws, DERIVED)
            _assert_plugin_enabled(ws)
            _snapshot_plugin_state(ws, run, tag="after-apply", extra={"import_done": False})

            # 1  V5  整个项目  WARM  ×3
            #    README 步骤 1。measure(WARM) 先 V3 import，再跑主场景。
            recs = run.measure(
                ws,
                group=GROUP,
                step="s1",
                cmd="V5",
                cache="WARM",
            )
            _snapshot_plugin_state(
                ws,
                run,
                tag="after-s1-warm",
                extra={"import_done": True, "from_step": recs[0].get("step_id")},
            )

            # 2  V2  uses_addon.gd  WARM  ×3
            #    README 步骤 2。ADD-USES：WARM check-only 是否找不到 DummySingleton。
            run.measure(
                ws,
                group=GROUP,
                step="s2",
                cmd="V2",
                cache="WARM",
                target="res://uses_addon.gd",
            )

            # 3  V2  uses_addon.gd  COLD  ×3
            #    README 步骤 3。冷态是否加剧（与 N01 COLD/WARM 对照）。
            run.measure(
                ws,
                group=GROUP,
                step="s3",
                cmd="V2",
                cache="COLD",
                target="res://uses_addon.gd",
            )

            # 4  V1  全项目哨兵  WARM  ×3
            #    README 步骤 4。项目级是否放大该 FP。COLD 之后会再 warm 一次。
            run.measure(
                ws,
                group=GROUP,
                step="s4",
                cmd="V1",
                cache="WARM",
            )

        run.finish(
            exports={
                "kind": "collection-pointer",
                "repeat": 3,
                "groups": [GROUP],
                "steps": ["s1", "s2", "s3", "s4"],
                "derived": DERIVED,
                "script_order_note": (
                    "s0=apply_derived 一次，无 measure；s1–s4 均在插件已启用的同一工作区"
                ),
            }
        )
    except (BlockedError, StaleError, ManualGateError, ProbeError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return 0


def _assert_fixture_plugin_disabled(ws: probe.Workspace) -> None:
    """apply 前工作区必须仍是 fixture 的未启用状态。"""
    text = (ws.path / "project.godot").read_text(encoding="utf-8")
    if "[editor_plugins]" in text or "[autoload]" in text:
        raise ProbeError("NP-ADDON 工作区在 apply_derived 前已含 plugin/autoload，拒绝继续")


def _assert_plugin_enabled(ws: probe.Workspace) -> None:
    text = (ws.path / "project.godot").read_text(encoding="utf-8")
    if "DummySingleton" not in text or "[editor_plugins]" not in text:
        raise ProbeError(
            "apply_derived 后 project.godot 缺少 DummySingleton 或 [editor_plugins]"
        )


def _snapshot_plugin_state(
    ws: probe.Workspace,
    run: probe.Run,
    *,
    tag: str,
    extra: dict,
) -> None:
    """N02 私事：记下 apply 后 / 第一次 WARM import 后的 autoload 与 uid。"""
    dest = run.artifact_root / GROUP / "plugin-state" / tag
    dest.mkdir(parents=True, exist_ok=True)
    project = ws.path / "project.godot"
    shutil.copy2(project, dest / "project.godot")
    uid_path = ws.path / SINGLETON_UID_REL
    uid_text = None
    if uid_path.is_file():
        shutil.copy2(uid_path, dest / "dummy_singleton.gd.uid")
        uid_text = uid_path.read_text(encoding="utf-8").strip()
    project_text = project.read_text(encoding="utf-8")
    meta = {
        "tag": tag,
        "expected_uid": EXPECTED_UID,
        "uid_file_exists": uid_path.is_file(),
        "uid_file_value": uid_text,
        "uid_matches_patch": uid_text == EXPECTED_UID if uid_text else False,
        "project_has_dummy_singleton": "DummySingleton" in project_text,
        "project_autoload_has_expected_uid": EXPECTED_UID in project_text,
        **extra,
    }
    (dest / "plugin-state.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    sys.exit(main())
