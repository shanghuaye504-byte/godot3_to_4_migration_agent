"""V3 懒触发 —— 方案文档 §2.1.3 伪代码的直译。

三个 phase 禁止合并：intake / iteration / final_gate。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from godot_mcp.verify_filter.models import ProjectFilterView
from godot_mcp.verify_shell.cache import cache_is_warm
from godot_mcp.verify_shell.diff import DiffView

Phase = Literal["intake", "iteration", "final_gate"]

CLASS_NAME_LINE = re.compile(r"^[+-]class_name\s")
_UID_DUP = re.compile(r"UID duplicate detected between")


def is_uid_duplicate_repair(
    diff: DiffView,
    previous_view: ProjectFilterView | None,
) -> bool:
    """本轮在修 UID 重复：diff 删了 `.uid`，或上一视图有 duplicate 根因且本轮动了那些路径。"""
    if diff.deleted_uid():
        return True
    if previous_view is None:
        return False
    touched = diff.all_paths()
    if not touched:
        return False
    for event in previous_view.root_cause_errors:
        if not _UID_DUP.search(event.message):
            continue
        if event.res_path and _res_to_rel(event.res_path) in touched:
            return True
    return False


def should_run_v3(
    workspace: Path,
    diff: DiffView,
    previous_view: ProjectFilterView | None,
    *,
    phase: Phase,
    v3_ran: bool,
    intake_needs_uid_wipe: bool = False,
) -> bool:
    """本 phase 要不要跑 V3。不启动 Godot。"""
    if phase == "intake":
        return (not cache_is_warm(workspace)) or intake_needs_uid_wipe
    if phase == "final_gate":
        if previous_view is None:
            return False
        return previous_view.gdscript_complete and not v3_ran
    if not cache_is_warm(workspace):
        return True
    if diff.line_matches(CLASS_NAME_LINE):
        return True
    if diff.added_gd_file():
        return True
    if diff.path_endswith((".gdshader", ".shader")):
        return True
    if diff.tres_hunk_mentions_shader():
        return True
    if is_uid_duplicate_repair(diff, previous_view):
        return True
    return False


def _res_to_rel(res_path: str) -> str:
    if res_path.startswith("res://"):
        return res_path[6:]
    return res_path
