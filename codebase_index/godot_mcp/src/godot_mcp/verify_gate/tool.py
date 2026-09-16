"""`run_verify_tool` —— 外壳编排 + Gate 判定。

对 LLM / MCP 而言这是黑盒：一次调用返回 `VerifyGateResult`。
内部子循环（V3 / V1↔V2 / 收尾门）在 `verify_shell` 里跑完，再交给 `evaluate`。

studio 一对一：不收 session / workspace / 成本 / diff 覆盖参数。phase、unified_diff、
patched_files 一律由本函数从单槽 state 与工作区快照算出。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from godot_mcp.config import Config, load_config
from godot_mcp.verify.runner import DEFAULT_TIMEOUT_S, VerifyResult, run_verify
from godot_mcp.verify_filter import filter_verify_output, merge_command_results, parse_autoload_keys
from godot_mcp.verify_filter.models import ClassifiedEvent, ProjectFilterView
from godot_mcp.verify_gate.algorithm import evaluate
from godot_mcp.verify_gate.config import RetryGateConfig, load_retry_gate_config
from godot_mcp.verify_gate.models import ProjectVerifyState, VerifyGateRequest, VerifyGateResult
from godot_mcp.verify_gate.state_store import InMemoryStateStore, StateStore
from godot_mcp.verify_shell.cache import cache_is_warm
from godot_mcp.verify_shell.check_file_annotate import (
    annotate_check_file_view,
    merge_shell_directive,
)
from godot_mcp.verify_shell.collect import MAX_V1_ROUNDS, MAX_V2_TARGETS, collect_workspace_view, empty_view
from godot_mcp.verify_shell.diff import parse_unified_diff
from godot_mcp.verify_shell.lock import WorkspaceBusyError, workspace_lock
from godot_mcp.verify_shell.reject import UnsupportedProjectError, reject_if_unsupported
from godot_mcp.verify_shell.snapshot import SnapshotTooLargeError, diff_snapshots, scan_workspace
from godot_mcp.verify_shell.trigger import Phase
from godot_mcp.verify_shell.uid import wipe_uid_sidecars

RunVerifyFn = Callable[[str, str | None, str, Path, int], VerifyResult]

_DEFAULT_STORE = InMemoryStateStore()
_KIND_TO_COMMAND: dict[str, Literal["V1", "V2"]] = {
    "check_file": "V2",
    "check_workspace": "V1",
}


def run_verify_tool(
    kind: str,
    target: str | None = None,
    *,
    config: Config | None = None,
    gate_cfg: RetryGateConfig | None = None,
    state_store: StateStore | None = None,
    run_verify_fn: RunVerifyFn | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    max_v1_rounds: int = MAX_V1_ROUNDS,
    max_v2_targets: int = MAX_V2_TARGETS,
) -> VerifyGateResult:
    """起 Godot → 外壳采集 → Gate 判定。一次调用对应一个 Agent round。"""
    if kind not in _KIND_TO_COMMAND:
        raise ValueError(f"unknown verify kind: {kind}")
    if kind == "check_file" and not target:
        raise ValueError("check_file requires a target file path")

    cfg = config or load_config()
    retry_cfg = gate_cfg or load_retry_gate_config()
    store = state_store or _DEFAULT_STORE
    spawn = run_verify_fn or _default_run_verify
    command = _KIND_TO_COMMAND[kind]

    state: ProjectVerifyState
    infra_status: Literal["OK", "TIMEOUT", "CRASH"]
    project_view: ProjectFilterView
    resolved_patched: frozenset[str]
    shell_directive: str | None

    try:
        with workspace_lock(cfg.project_root):
            reject_if_unsupported(cfg.project_root)
            state = store.load()
            resolved_phase: Phase = "intake" if state.rounds_used == 0 else "iteration"
            infra_status, project_view, resolved_patched, shell_directive = _run_locked(
                kind=kind,
                target=target,
                cfg=cfg,
                spawn=spawn,
                timeout_s=timeout_s,
                state=state,
                resolved_phase=resolved_phase,
                max_v1_rounds=max_v1_rounds,
                max_v2_targets=max_v2_targets,
            )
    except WorkspaceBusyError as exc:
        raise ValueError(str(exc)) from exc
    except (UnsupportedProjectError, SnapshotTooLargeError):
        raise

    request = VerifyGateRequest(
        command="MERGED" if command == "V1" else command,
        project_view=project_view,
        patched_files=resolved_patched,
        infra_status=infra_status,
    )
    result = evaluate(state, request, retry_cfg)
    store.save(state)
    # directive 不进 state：硬停止清空；Gate 软提示优先于 check_file 外壳 A/B。
    return replace(
        result,
        directive=merge_shell_directive(
            hard_stop=result.hard_stop,
            gate_directive=result.directive,
            shell_directive=shell_directive,
        ),
    )


def _run_locked(
    *,
    kind: str,
    target: str | None,
    cfg: Config,
    spawn: RunVerifyFn,
    timeout_s: int,
    state: ProjectVerifyState,
    resolved_phase: Phase,
    max_v1_rounds: int,
    max_v2_targets: int,
) -> tuple[Literal["OK", "TIMEOUT", "CRASH"], ProjectFilterView, frozenset[str], str | None]:
    if kind == "check_file":
        return _run_check_file(target, cfg, spawn, timeout_s)

    if resolved_phase == "intake":
        wipe_uid_sidecars(cfg.project_root)
    current_snapshot = scan_workspace(cfg.project_root)
    diff_text = diff_snapshots(state.source_snapshot, current_snapshot)
    parsed = parse_unified_diff(diff_text)
    resolved_patched = frozenset(_as_res(path) for path in parsed.all_paths())
    collected = collect_workspace_view(
        project_root=cfg.project_root,
        godot_binary=cfg.godot_binary,
        spawn=spawn,
        timeout_s=timeout_s,
        unified_diff=diff_text,
        phase=resolved_phase,
        previous_view=state.previous_view,
        intake_needs_uid_wipe=(resolved_phase == "intake"),
        max_v1_rounds=max_v1_rounds,
        max_v2_targets=max_v2_targets,
    )
    state.source_snapshot = current_snapshot
    state.previous_view = collected.project_view
    return collected.infra_status, collected.project_view, resolved_patched, None


def _run_check_file(
    target: str | None,
    cfg: Config,
    spawn: RunVerifyFn,
    timeout_s: int,
) -> tuple[Literal["OK", "TIMEOUT", "CRASH"], ProjectFilterView, frozenset[str], str | None]:
    resolved_patched: frozenset[str] = frozenset()
    if not cache_is_warm(cfg.project_root):
        raw_v3 = spawn("V3", None, cfg.godot_binary, cfg.project_root, timeout_s)
        infra = _infra_of(raw_v3)
        if infra != "OK":
            return infra, empty_view(f"infra:{infra}"), resolved_patched, None
    raw = spawn("V2", target, cfg.godot_binary, cfg.project_root, timeout_s)
    infra_status, project_view, shell_directive = _collect_file_view(raw, cfg.project_root)
    return infra_status, project_view, resolved_patched, shell_directive


def _as_res(path: str) -> str:
    if path.startswith("res://"):
        return path
    return f"res://{path}"


def _infra_of(raw: VerifyResult) -> Literal["OK", "TIMEOUT", "CRASH"]:
    if raw.timed_out:
        return "TIMEOUT"
    if raw.exit_code is None:
        return "CRASH"
    return "OK"


def gate_result_to_dict(result: VerifyGateResult) -> dict[str, Any]:
    """把 `VerifyGateResult` 收成 MCP / JSON 可序列化的字典。"""
    return {
        "project_status": result.project_status,
        "root_cause_errors": [_event_to_dict(event) for event in result.root_cause_errors],
        "pointers": [_event_to_dict(event) for event in result.pointers],
        "caveats": list(result.caveats),
        "untrusted_files": sorted(result.untrusted_files),
        "gdscript_complete": result.gdscript_complete,
        "shader_checked": result.shader_checked,
        "probe_incomplete": result.probe_incomplete,
        "round_index": result.round_index,
        "signature_set": sorted(result.signature_set),
        "diff": {
            "new_signatures": sorted(result.diff.new_signatures),
            "resolved_signatures": sorted(result.diff.resolved_signatures),
            "persisted_signatures": sorted(result.diff.persisted_signatures),
        },
        "decision": result.decision,
        "hard_stop": result.hard_stop,
        "reason": result.reason,
        "directive": result.directive,
        "remaining_budget": {
            "rounds_used": result.remaining_budget.rounds_used,
            "rounds_limit": result.remaining_budget.rounds_limit,
        },
    }


def _default_run_verify(
    kind: str,
    target: str | None,
    godot_binary: str,
    project_root: Path,
    timeout_s: int,
) -> VerifyResult:
    return run_verify(kind, target, godot_binary, project_root, timeout_s=timeout_s)


def _collect_file_view(
    raw: VerifyResult,
    project_root: Path,
) -> tuple[Literal["OK", "TIMEOUT", "CRASH"], ProjectFilterView, str | None]:
    if raw.timed_out:
        return "TIMEOUT", empty_view("infra:TIMEOUT"), None
    if raw.exit_code is None:
        return "CRASH", empty_view("infra:CRASH"), None
    godot_file = project_root / "project.godot"
    keys = (
        parse_autoload_keys(godot_file.read_text(encoding="utf-8"))
        if godot_file.is_file()
        else frozenset()
    )
    primary = filter_verify_output(
        raw.stdout,
        raw.stderr,
        command="V2",
        autoload_keys=keys,
    )
    view = merge_command_results(primary, {})
    # 仅 check_file：class cache 陈旧则挪 Identifier；非白名单 compile Identifier 打 B caveat。
    annotated = annotate_check_file_view(
        view,
        project_root=project_root,
        autoload_keys=keys,
    )
    return "OK", annotated.view, annotated.directive


def _event_to_dict(event: ClassifiedEvent) -> dict[str, Any]:
    return {
        "kind": event.kind,
        "message": event.message,
        "res_path": event.res_path,
        "line": event.line_in_project,
        "symbol": event.symbol,
        "local_signature": event.local_signature,
        "role": event.role,
        "target_res_path": event.target_res_path,
    }
