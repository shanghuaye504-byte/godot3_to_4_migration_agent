"""一轮 workspace 采集：条件 V3 → V1↔V2 收敛 → 收尾门 V3。

方案文档 §2.1.3 / §7.10。本模块通过注入的 `spawn` 起进程，测试里 mock 即可。
单次 V2 超时/崩溃不把整轮打成 INFRA；V1 / 迭代 V3 / 收尾 V3 失败则整轮 INFRA。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from godot_mcp.verify.runner import VerifyResult
from godot_mcp.verify_filter import filter_verify_output, merge_command_results, parse_autoload_keys
from godot_mcp.verify_filter.models import CommandKind, FilterResult, ProjectFilterView
from godot_mcp.verify_shell.diff import parse_unified_diff
from godot_mcp.verify_shell.trigger import Phase, should_run_v3

RunVerifyFn = Callable[[str, str | None, str, Path, int], VerifyResult]

MAX_V1_ROUNDS = 8
MAX_V2_TARGETS = 8


@dataclass(frozen=True)
class CollectionResult:
    infra_status: Literal["OK", "TIMEOUT", "CRASH"]
    project_view: ProjectFilterView
    v3_ran: bool
    v1_rounds: int


def collect_workspace_view(
    *,
    project_root: Path,
    godot_binary: str,
    spawn: RunVerifyFn,
    timeout_s: int,
    unified_diff: str = "",
    phase: Phase = "iteration",
    previous_view: ProjectFilterView | None = None,
    intake_needs_uid_wipe: bool = False,
    max_v1_rounds: int = MAX_V1_ROUNDS,
    max_v2_targets: int = MAX_V2_TARGETS,
) -> CollectionResult:
    """跑完一轮内部子循环，返回交给 Gate 的最终 `ProjectFilterView`。"""
    keys = _load_autoload_keys(project_root)
    diff = parse_unified_diff(unified_diff)
    v3_result: FilterResult | None = None
    v3_ran = False

    if should_run_v3(
        project_root,
        diff,
        previous_view,
        phase=phase,
        v3_ran=False,
        intake_needs_uid_wipe=intake_needs_uid_wipe,
    ):
        raw = spawn("V3", None, godot_binary, project_root, timeout_s)
        infra = _infra_of(raw)
        if infra != "OK":
            return CollectionResult(infra, empty_view(f"infra:{infra}"), True, 0)
        v3_result = _filter(raw, "V3", keys)
        v3_ran = True

    v2_by_target: dict[str, FilterResult] = {}
    v1: FilterResult | None = None
    v1_rounds = 0

    for _ in range(max_v1_rounds):
        raw = spawn("V1", None, godot_binary, project_root, timeout_s)
        infra = _infra_of(raw)
        if infra != "OK":
            return CollectionResult(infra, empty_view(f"infra:{infra}"), v3_ran, v1_rounds)
        v1 = _filter(raw, "V1", keys)
        v1_rounds += 1
        added = _drill_new_pointers(
            v1,
            v2_by_target,
            spawn=spawn,
            godot_binary=godot_binary,
            project_root=project_root,
            timeout_s=timeout_s,
            autoload_keys=keys,
            max_v2_targets=max_v2_targets,
        )
        if not added:
            break

    if v1 is None:
        return CollectionResult("OK", empty_view("no_v1"), v3_ran, 0)

    view = merge_command_results(v1, v2_by_target, v3_result)

    if should_run_v3(
        project_root,
        diff,
        view,
        phase="final_gate",
        v3_ran=v3_ran,
    ):
        raw = spawn("V3", None, godot_binary, project_root, timeout_s)
        infra = _infra_of(raw)
        if infra != "OK":
            return CollectionResult(infra, empty_view(f"infra:{infra}"), True, v1_rounds)
        v3_result = _filter(raw, "V3", keys)
        v3_ran = True
        view = merge_command_results(v1, v2_by_target, v3_result)

    view = _annotate_pointer_caveats(
        view,
        v2_count=len(v2_by_target),
        v1_rounds=v1_rounds,
        max_v1_rounds=max_v1_rounds,
        max_v2_targets=max_v2_targets,
    )
    return CollectionResult("OK", view, v3_ran, v1_rounds)


def empty_view(caveat: str) -> ProjectFilterView:
    return ProjectFilterView(
        status="CLEAN",
        root_cause_errors=[],
        pending_pointers=[],
        symptoms=[],
        dropped=[],
        caveats=[caveat],
        untrusted_files=frozenset(),
        gdscript_complete=False,
        shader_checked=False,
    )


def _annotate_pointer_caveats(
    view: ProjectFilterView,
    *,
    v2_count: int,
    v1_rounds: int,
    max_v1_rounds: int,
    max_v2_targets: int,
) -> ProjectFilterView:
    """未消化 pointer 时显式标记：预算打满 vs 单次 V2 跳过。"""
    if not view.pending_pointers:
        return view
    hit_budget = v2_count >= max_v2_targets or v1_rounds >= max_v1_rounds
    extra = "pointer_budget_exhausted" if hit_budget else "pointer_probe_incomplete"
    if extra in view.caveats:
        return view
    return replace(view, caveats=[*view.caveats, extra])


def _drill_new_pointers(
    primary: FilterResult,
    v2_by_target: dict[str, FilterResult],
    *,
    spawn: RunVerifyFn,
    godot_binary: str,
    project_root: Path,
    timeout_s: int,
    autoload_keys: frozenset[str],
    max_v2_targets: int,
) -> int:
    """对尚未 V2 过的 pointer 下钻。返回本轮新增的 V2 次数。"""
    added = 0
    for pointer in primary.pointers:
        target = pointer.target_res_path
        if not target or target in v2_by_target:
            continue
        if len(v2_by_target) >= max_v2_targets:
            break
        raw = spawn("V2", target, godot_binary, project_root, timeout_s)
        if _infra_of(raw) != "OK":
            continue
        v2_by_target[target] = _filter(raw, "V2", autoload_keys)
        added += 1
    return added


def _filter(raw: VerifyResult, command: CommandKind, keys: frozenset[str]) -> FilterResult:
    return filter_verify_output(
        raw.stdout,
        raw.stderr,
        command=command,
        autoload_keys=keys,
    )


def _infra_of(raw: VerifyResult) -> Literal["OK", "TIMEOUT", "CRASH"]:
    if raw.timed_out:
        return "TIMEOUT"
    if raw.exit_code is None:
        return "CRASH"
    return "OK"


def _load_autoload_keys(project_root: Path) -> frozenset[str]:
    godot_file = Path(project_root) / "project.godot"
    if not godot_file.is_file():
        return frozenset()
    return parse_autoload_keys(godot_file.read_text(encoding="utf-8"))
