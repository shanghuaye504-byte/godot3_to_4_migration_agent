#!/usr/bin/env python3
"""N01 正式采集脚本：autoload 假阳性（#78587）。P1-4。

按 README.md P1-4 采集；步骤 2/3 仅在本脚本内对调为「先冷态 V5 证明
Config 存在，再 V3 建 WARM」。不改 README 步骤表编号。

同一份 NP-AUTOLOAD 工作区、不可并行、不可重排。shadow_config 只在临时
工作区改名启用；禁止启用 res_loader.gd.disabled。

本脚本只落盘，不下结论（不写 CONFIRMED / 三种过滤策略裁决）。
假 Godot 禁止用于本实验。CleanControl BG 用 N09 已落盘日志，本实验不重跑。

人读日志时的两种文案必须分开：
- AL-USES（filterable）：Identifier not found: Config（或近义）
- AL-SHADOW（不可过滤）：Class "Config" hides an autoload singleton
fixture 运行时打印 CONFIG_ALIVE / NP_AUTOLOAD_MAIN_OK，不是 issue 原文
里的 Config.ping() called。
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

N = "N01"
FIXTURES = ("phase1/NP-AUTOLOAD",)
GROUP = "np-autoload"
SHADOW_DISABLED = "shadow_config.gd.disabled"
SHADOW_ENABLED = "shadow_config.gd"
RES_LOADER_DISABLED = "res_loader.gd.disabled"
RES_LOADER_ENABLED = "res_loader.gd"


def main() -> int:
    os.environ.pop("PROBE_GODOT", None)

    try:
        run = probe.start(
            N,
            repeat_default=3,
            timeout_seconds=30,
            fixtures=FIXTURES,
            depends_on=("N09", "N08", "N03"),
        )
        if run.identity.fake:
            raise ProbeError(
                "BLOCKED: N01 正式采集禁止假 Godot。"
                f" 当前可执行文件是 {run.identity.path}"
            )

        with probe.workspace("phase1/NP-AUTOLOAD", group=GROUP) as ws:
            _assert_disabled_layout(ws)

            # 1  V2  uses_autoload.gd  COLD  ×3
            #    README 步骤 1。AL-USES：冷态是否 Identifier not found: Config
            run.measure(
                ws,
                group=GROUP,
                step="s1",
                cmd="V2",
                cache="COLD",
                target="res://uses_autoload.gd",
            )

            # 2  V5  整个项目  COLD  ×3
            #    README 步骤 3，脚本内提前并改为 COLD：运行时证明 Config 存在，
            #    且不依赖先验 import。stdout 看 CONFIG_ALIVE / NP_AUTOLOAD_MAIN_OK。
            run.measure(
                ws,
                group=GROUP,
                step="s2",
                cmd="V5",
                cache="COLD",
            )

            # 3  V3  整个项目  COLD  ×1
            #    README 步骤 2，脚本内后移。建 WARM；成功后写 marker。
            recs = run.measure(
                ws,
                group=GROUP,
                step="s3",
                cmd="V3",
                cache="COLD",
                repeat=1,
            )
            _mark_warm(ws, recs[0])

            # 4  V2  uses_autoload.gd  WARM  ×3
            #    README 步骤 4。决策分叉：WARM 下 FP 是否还在。
            run.measure(
                ws,
                group=GROUP,
                step="s4",
                cmd="V2",
                cache="WARM",
                target="res://uses_autoload.gd",
            )

            # 5  V1  全项目哨兵  WARM  ×3
            #    README 步骤 5。项目级是否放大 FP。旧编号 V9 已并入 V1。
            run.measure(
                ws,
                group=GROUP,
                step="s5",
                cmd="V1",
                cache="WARM",
            )

            # 6  rename 启用 shadow_config.gd（埋点 AL-SHADOW）
            #    README 步骤 6。不进 util、不启 Godot。禁止同时启用 res_loader。
            _enable_shadow(ws)

            # 7  V2  shadow_config.gd  WARM  ×3
            #    README 步骤 7。真错误：Class "Config" hides an autoload singleton
            run.measure(
                ws,
                group=GROUP,
                step="s7",
                cmd="V2",
                cache="WARM",
                target="res://shadow_config.gd",
            )

            # 8  V5  整个项目  WARM  ×3
            #    README 步骤 8。真冲突启用后运行时是否仍正常；与 s2 对照。
            run.measure(
                ws,
                group=GROUP,
                step="s8",
                cmd="V5",
                cache="WARM",
            )

        run.finish(
            exports={
                "kind": "collection-pointer",
                "repeat": 3,
                "groups": [GROUP],
                "steps": ["s1", "s2", "s3", "s4", "s5", "s7", "s8"],
                "script_order_note": (
                    "s2=V5 COLD then s3=V3（README 步骤 2/3 仅在本脚本对调）；"
                    "s6=workspace rename shadow_config.gd.disabled，无 measure"
                ),
            }
        )
    except (BlockedError, StaleError, ProbeError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return 0


def _assert_disabled_layout(ws: probe.Workspace) -> None:
    """进入工作区时两个埋点必须仍是 .disabled，且没有已启用副本。"""
    if not (ws.path / SHADOW_DISABLED).is_file():
        raise ProbeError(f"缺少 {SHADOW_DISABLED}")
    if (ws.path / SHADOW_ENABLED).exists():
        raise ProbeError(f"fixture 不得预启用 {SHADOW_ENABLED}")
    if not (ws.path / RES_LOADER_DISABLED).is_file():
        raise ProbeError(f"缺少 {RES_LOADER_DISABLED}")
    if (ws.path / RES_LOADER_ENABLED).exists():
        raise ProbeError(f"禁止启用 {RES_LOADER_ENABLED}")


def _enable_shadow(ws: probe.Workspace) -> None:
    """s6：只启用 AL-SHADOW。N01 私事，不进 util。"""
    if (ws.path / RES_LOADER_ENABLED).exists():
        raise ProbeError(f"禁止启用 {RES_LOADER_ENABLED}")
    src = ws.path / SHADOW_DISABLED
    dest = ws.path / SHADOW_ENABLED
    if not src.is_file():
        raise ProbeError(f"找不到 {SHADOW_DISABLED}，无法启用 AL-SHADOW")
    if dest.exists():
        raise ProbeError(f"{SHADOW_ENABLED} 已存在，拒绝覆盖")
    src.rename(dest)
    if (ws.path / RES_LOADER_ENABLED).exists():
        raise ProbeError(f"rename 后出现了 {RES_LOADER_ENABLED}")


def _mark_warm(ws: probe.Workspace, rec: dict) -> None:
    """s3 的 V3 已建好缓存；写 marker，避免后续 WARM 再跑一次 import。"""
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
