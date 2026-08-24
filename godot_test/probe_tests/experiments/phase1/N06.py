#!/usr/bin/env python3
"""N06 正式采集脚本：invalid UID 严重度与资源引用变更后的 import 触发。P1-8。

按 README.md P1-8 采集。全程一个 NP-RESOURCE 工作区、严格按序。
步骤 1 消费 derived/NP-RESOURCE@uid-baseline；伪造 UID 与改 ext_resource
只发生在临时工作区，不写回 fixture。

从本实验起注入 np-warn-debug.ini，stdout 与 stderr 都看 WARNING:。
不跑 V8。本脚本只落盘，不下结论（不写 CONFIRMED）。
假 Godot 禁止用于本实验。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

PROBE_ROOT = Path(__file__).resolve().parents[2]
if str(PROBE_ROOT) not in sys.path:
    sys.path.insert(0, str(PROBE_ROOT))

from experiments.util import probe  # noqa: E402
from experiments.util.probe import (  # noqa: E402
    WARM_MARKER,
    BlockedError,
    ManualGateError,
    ProbeError,
    StaleError,
)

N = "N06"
FIXTURES = ("phase1/NP-RESOURCE",)
DERIVED = "NP-RESOURCE@uid-baseline"
FRAGMENT = "np-warn-debug.ini"
GROUP = "np-resource"
FAKE_UID = "uid://n06forgedinvalid"
SUB_SCENE_UID = "uid://c66i7tbgxdem6"
OTHER_SCENE_UID = "uid://n06otherbase01"
UID_RE = re.compile(r"uid://[A-Za-z0-9]+")
UID_FILES = ("main.tscn", "sub.tscn", "sub.gd.uid", "project.godot")


def main() -> int:
    os.environ.pop("PROBE_GODOT", None)

    try:
        run = probe.start(
            N,
            repeat_default=3,
            timeout_seconds=30,
            fixtures=FIXTURES,
            derived=(DERIVED,),
            depends_on=("N09", "N08", "N03"),
        )
        if run.identity.fake:
            raise ProbeError(
                "BLOCKED: N06 正式采集禁止假 Godot。"
                f" 当前可执行文件是 {run.identity.path}"
            )

        with probe.workspace("phase1/NP-RESOURCE", group=GROUP) as ws:
            _assert_fixture_has_no_uid(ws)

            # 1  apply_derived：正确 UID 基线
            probe.apply_derived(ws, DERIVED)
            _assert_uid_baseline(ws)
            probe.settings(ws, FRAGMENT)
            baseline = _read_uid_files(ws)
            _snapshot(ws, run, "s1-after-apply", extra={"settings": FRAGMENT})

            # 2  V3  整个项目  COLD  ×1
            recs = run.measure(
                ws,
                group=GROUP,
                step="s2",
                cmd="V3",
                cache="COLD",
                repeat=1,
            )
            _mark_warm(ws, recs[-1])
            _snapshot(ws, run, "s2-after-import")

            # 3  V1  全项目哨兵  WARM  ×3
            run.measure(
                ws,
                group=GROUP,
                step="s3",
                cmd="V1",
                cache="WARM",
            )

            # 4  伪造 .uid / .tscn 里的 uid://
            forged = _corrupt_uid(ws)
            _snapshot(ws, run, "s4-after-corrupt", extra={"forged": forged})

            # 5  V2  sub.gd  WARM  ×3
            run.measure(
                ws,
                group=GROUP,
                step="s5",
                cmd="V2",
                cache="WARM",
                target="res://sub.gd",
            )

            # 6  V1  全项目哨兵  WARM  ×3
            run.measure(
                ws,
                group=GROUP,
                step="s6",
                cmd="V1",
                cache="WARM",
            )

            # 7  V3  整个项目  WARM  ×3
            run.measure(
                ws,
                group=GROUP,
                step="s7",
                cmd="V3",
                cache="WARM",
            )
            _snapshot(ws, run, "s7-after-reimport")

            # 8  V1  全项目哨兵  WARM  ×3
            run.measure(
                ws,
                group=GROUP,
                step="s8",
                cmd="V1",
                cache="WARM",
            )

            # 8b 伪造 UID 会让后续 WARM V3 失败；替换 ext_resource 前先恢复录制基线。
            _restore_uid(ws, baseline)
            _snapshot(ws, run, "s8b-uid-restored")
            recs = run.measure(
                ws,
                group=GROUP,
                step="s8b",
                cmd="V3",
                cache="WARM",
                repeat=1,
            )
            _mark_warm(ws, recs[-1])
            _snapshot(ws, run, "s8b-after-restore-import")

            # 9  把 main.tscn 的 ext_resource 指到另一路径
            retarget = _retarget_ext_resource(ws)
            _snapshot(ws, run, "s9-after-retarget", extra={"retarget": retarget})

            # 10  V1  全项目哨兵（不 import）  WARM  ×3
            run.measure(
                ws,
                group=GROUP,
                step="s10",
                cmd="V1",
                cache="WARM",
            )

            # 11  V3  整个项目  WARM  ×1
            run.measure(
                ws,
                group=GROUP,
                step="s11",
                cmd="V3",
                cache="WARM",
                repeat=1,
            )
            _snapshot(ws, run, "s11-after-reimport")

            # 12  V1  全项目哨兵  WARM  ×3
            run.measure(
                ws,
                group=GROUP,
                step="s12",
                cmd="V1",
                cache="WARM",
            )

        run.finish(
            exports={
                "kind": "collection-pointer",
                "repeat": 3,
                "groups": [GROUP],
                "steps": [
                    "s1",
                    "s2",
                    "s3",
                    "s4",
                    "s5",
                    "s6",
                    "s7",
                    "s8",
                    "s8b",
                    "s9",
                    "s10",
                    "s11",
                    "s12",
                ],
                "derived": DERIVED,
                "fragment": FRAGMENT,
                "fake_uid": FAKE_UID,
                "script_order_note": (
                    "s1=apply_derived+settings，无 measure；"
                    "s4=corrupt_uid；s8b=恢复录制 UID 后再 V3；"
                    "s9=retarget ext_resource；s2/s8b/s11 repeat=1；"
                    "stdout 与 stderr 都看 WARNING:"
                ),
            }
        )
    except (BlockedError, StaleError, ManualGateError, ProbeError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return 0


def _assert_fixture_has_no_uid(ws: probe.Workspace) -> None:
    """apply 前工作区必须仍是 fixture：场景里没有 uid://。"""
    main = (ws.path / "main.tscn").read_text(encoding="utf-8")
    if "uid://" in main or (ws.path / "sub.gd.uid").is_file():
        raise ProbeError("NP-RESOURCE 工作区在 apply_derived 前已含 UID，拒绝继续")


def _assert_uid_baseline(ws: probe.Workspace) -> None:
    main = (ws.path / "main.tscn").read_text(encoding="utf-8")
    sub = (ws.path / "sub.tscn").read_text(encoding="utf-8")
    if "uid://c66i7tbgxdem6" not in main:
        raise ProbeError("apply_derived 后 main.tscn 缺少 sub.tscn 的 uid")
    if "uid://dvemcuu87n1e2" not in sub:
        raise ProbeError("apply_derived 后 sub.tscn 缺少 sub.gd 的 uid")
    uid_path = ws.path / "sub.gd.uid"
    if not uid_path.is_file():
        raise ProbeError("apply_derived 后缺少 sub.gd.uid")
    if uid_path.read_text(encoding="utf-8").strip() != "uid://dvemcuu87n1e2":
        raise ProbeError("apply_derived 后 sub.gd.uid 与 provenance 不一致")


def _uids_in(text: str) -> list[str]:
    return UID_RE.findall(text)


def _corrupt_uid(ws: probe.Workspace) -> dict[str, dict[str, list[str]]]:
    """N06 私事：把工作区 .uid / .tscn 里的 uid:// 改成伪造值。"""
    changed: dict[str, dict[str, list[str]]] = {}
    for rel in ("main.tscn", "sub.tscn", "sub.gd.uid"):
        path = ws.path / rel
        text = path.read_text(encoding="utf-8")
        before = _uids_in(text)
        new = UID_RE.sub(FAKE_UID, text)
        if new != text:
            path.write_text(new, encoding="utf-8")
            after = _uids_in(new)
            changed[rel] = {"before": before, "after": after}
    if not changed:
        raise ProbeError("corrupt_uid 没有改到任何 uid://")
    return changed


def _read_uid_files(ws: probe.Workspace) -> dict[str, str]:
    return {
        rel: (ws.path / rel).read_text(encoding="utf-8")
        for rel in ("main.tscn", "sub.tscn", "sub.gd.uid")
    }


def _restore_uid(ws: probe.Workspace, baseline: dict[str, str]) -> None:
    """把 .tscn / .uid 写回 apply_derived 后的录制基线。"""
    for rel, text in baseline.items():
        (ws.path / rel).write_text(text, encoding="utf-8")
    extra = ws.path / "other.tscn"
    if extra.is_file():
        extra.unlink()
    _assert_uid_baseline(ws)


def _retarget_ext_resource(ws: probe.Workspace) -> dict[str, str]:
    """N06 私事：main.tscn 的 ext_resource 改指 res://other.tscn。

    拷贝后只改 other.tscn 自己的场景 UID，避免和 sub.tscn 撞车；
    main 的 ext_resource 仍保留对 sub 的 uid，只改 path。
    """
    src = ws.path / "sub.tscn"
    dest = ws.path / "other.tscn"
    shutil.copy2(src, dest)
    other = dest.read_text(encoding="utf-8")
    if f'uid="{SUB_SCENE_UID}"' not in other:
        raise ProbeError("retarget 时 sub.tscn 副本缺少录制的场景 UID")
    dest.write_text(
        other.replace(f'uid="{SUB_SCENE_UID}"', f'uid="{OTHER_SCENE_UID}"', 1),
        encoding="utf-8",
    )
    main = ws.path / "main.tscn"
    text = main.read_text(encoding="utf-8")
    if 'path="res://sub.tscn"' not in text:
        raise ProbeError("retarget 时 main.tscn 已没有 res://sub.tscn")
    main.write_text(
        text.replace('path="res://sub.tscn"', 'path="res://other.tscn"'),
        encoding="utf-8",
    )
    return {
        "from": "res://sub.tscn",
        "to": "res://other.tscn",
        "other_copied_from": "sub.tscn",
        "other_scene_uid": OTHER_SCENE_UID,
        "main_ext_resource_uid_kept": SUB_SCENE_UID,
    }


def _snapshot(
    ws: probe.Workspace,
    run: probe.Run,
    tag: str,
    extra: dict | None = None,
) -> None:
    dest = run.artifact_root / GROUP / "snapshots" / tag
    dest.mkdir(parents=True, exist_ok=True)
    uids: dict[str, list[str]] = {}
    for rel in (*UID_FILES, "other.tscn"):
        src = ws.path / rel
        if not src.is_file():
            continue
        shutil.copy2(src, dest / Path(rel).name)
        uids[rel] = _uids_in(src.read_text(encoding="utf-8"))
    meta = {"tag": tag, "uids": uids, **(extra or {})}
    (dest / "snapshot.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _mark_warm(ws: probe.Workspace, rec: dict) -> None:
    """s2 的 V3 已建好缓存；写 marker，避免后续 WARM 再偷偷 import。"""
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
