"""实验编排器（唯一编排入口，唯一允许维护跨步骤可变状态的模块）。

流程：加载 N 的 YAML -> 每个 group 独立 clone workspace + git 基线 ->
按 group 内 steps 顺序解析 cache_state -> 应用 hooks -> 解析 argv ->
按 repeat 循环调 capture.run_measurement -> 落盘 artifacts（含纵向 evaluation）
-> V3 成功后 mark_warm -> finally 无条件 cleanup。全部 group 跑完后做一次
跨 group 的横向 diff（仅 stability 类型），dispatch 到 analyzer 产出实验级
evaluation.json。
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Optional

from . import artifacts, cache, capture, cleanup, commands, digest, schema, workspace
from .types import CacheState, EngineProfile, Measurement
from ..analyzers import base as analyzer_base
from ..analyzers import normalize
from ..analyzers import stability  # noqa: F401  (import 触发 register("stability", ...))
from ..hooks import registry as hook_registry

PROBE_ROOT = Path(__file__).resolve().parents[2]

_WARM_TRIGGER_COMMANDS = ("V3", "V7_V3")


def _resolve_engine_profile(raw: dict) -> EngineProfile:
    executable = tuple(raw.get("executable", ["/usr/local/bin/godot4"]))
    return EngineProfile(
        executable=executable,
        version=raw.get("version", ""),
        build_hash=raw.get("build_hash", ""),
        fake=bool(raw.get("fake", False)),
    )


def _find_experiment_yaml(experiments_root: Path, exp_id: str) -> Path:
    for phase_dir in sorted(p for p in experiments_root.iterdir() if p.is_dir()):
        candidate = phase_dir / f"{exp_id}.yaml"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"找不到实验 YAML: {exp_id} (searched under {experiments_root})")


def _last_success(raws: list) -> bool:
    if not raws:
        return False
    last = raws[-1]
    return last.process.returncode == 0 and not last.process.timed_out and last.process.signal is None


def _group_common_command_at_warm(spec, results_by_group_step: dict) -> dict:
    by_command: dict = {}
    for group in spec.groups:
        for step in group.steps:
            if step.cache_state != CacheState.WARM:
                continue
            raws = results_by_group_step.get((group.group_id, step.step_id), [])
            by_command.setdefault(step.command, {}).setdefault(group.group_id, []).extend(raws)
    return {command: groups for command, groups in by_command.items() if len(groups) >= 2}


def _run_step_repeats(
    step,
    *,
    group,
    ws: Path,
    profiles: dict,
    engine_profile: EngineProfile,
    run_id: str,
    exp_id: str,
    artifacts_root: Path,
    rules,
    tracked_pgids: list,
) -> list:
    raws = []
    for repeat_idx in range(step.repeat):
        invocations = hook_registry.apply_hooks(
            step.hooks, workspace=ws, context={"step_id": step.step_id, "repeat_idx": repeat_idx}
        )
        try:
            argv = commands.resolve_command(
                step.command,
                profiles=profiles,
                engine_profile=engine_profile,
                project_path=ws,
                script=step.script,
                extra_flags=step.extra_flags,
            )
            if argv and isinstance(argv[0], list):
                raise NotImplementedError(
                    f"{step.command} 的多进程 fanout（如 V10）本轮范围之外"
                )

            measurement = Measurement(
                project=group.fixture,
                command=step.command,
                cache_state=step.cache_state,
                repeat_idx=repeat_idx,
            )
            raw = capture.run_measurement(
                argv,
                ws=ws,
                timeout_seconds=step.timeout_seconds,
                env=None,
                measurement=measurement,
                step_id=step.step_id,
                hooks_applied=[inv.name for inv in invocations],
                inputs_digest="",
            )
            tracked_pgids.append(raw.process.pgid)
            raws.append(raw)
        finally:
            hook_registry.revoke_hooks(invocations)

    vertical_eval = stability.evaluate_vertical(raws, rules)
    for repeat_idx, raw in enumerate(raws):
        directory = artifacts.step_artifact_dir(
            artifacts_root, run_id, exp_id, step.step_id, step.cache_state.value, repeat_idx
        )
        signatures = normalize.compute_signatures(
            normalize.parse_output_lines(raw.stdout) + normalize.parse_output_lines(raw.stderr), rules
        )
        cache_manifest = {"cache_state": step.cache_state.value, "is_warm": cache.is_warm(ws)}
        artifacts.write_step_artifacts(
            directory,
            raw,
            signatures,
            {"vertical": vertical_eval},
            cache_manifest,
            dataclasses.asdict(engine_profile),
        )
    return raws


def run_experiment(
    exp_id: str,
    *,
    run_id: str,
    experiments_root: Optional[Path] = None,
    common_dir: Optional[Path] = None,
    fixtures_root: Optional[Path] = None,
    workspaces_root: Optional[Path] = None,
    artifacts_root: Optional[Path] = None,
) -> dict:
    experiments_root = Path(experiments_root or PROBE_ROOT / "experiments")
    common_dir = Path(common_dir or experiments_root / "common")
    fixtures_root = Path(fixtures_root or PROBE_ROOT / "fixtures")
    workspaces_root = Path(workspaces_root or PROBE_ROOT / "workspaces")
    artifacts_root = Path(artifacts_root or PROBE_ROOT / "artifacts")

    spec_path = _find_experiment_yaml(experiments_root, exp_id)
    spec = schema.load_experiment(spec_path, common_dir=common_dir)

    engine_profile = _resolve_engine_profile(spec.engine_profile)
    profiles = commands.load_command_profiles(common_dir)
    rules = normalize.load_signature_rules(common_dir / "signature-rules.yaml")

    results_by_group_step: dict = {}
    group_summaries = []

    for group in spec.groups:
        fixture_dir = fixtures_root / group.fixture
        fixture_hash = digest.compute_tree_hash(fixture_dir)
        ws: Optional[Path] = None
        tracked_pgids: list = []
        try:
            ws = workspace.create_workspace(fixture_dir, workspaces_root, run_id, exp_id, group.group_id)
            workspace.git_init_baseline(ws)

            for step in group.steps:
                cache.resolve_cache_state(step.cache_state, ws)
                raws = _run_step_repeats(
                    step,
                    group=group,
                    ws=ws,
                    profiles=profiles,
                    engine_profile=engine_profile,
                    run_id=run_id,
                    exp_id=exp_id,
                    artifacts_root=artifacts_root,
                    rules=rules,
                    tracked_pgids=tracked_pgids,
                )
                results_by_group_step[(group.group_id, step.step_id)] = raws
                if step.command in _WARM_TRIGGER_COMMANDS and _last_success(raws):
                    cache.mark_warm(ws, step.step_id)

            group_summaries.append({"group_id": group.group_id, "status": "OK"})
        except Exception as exc:  # noqa: BLE001 - 记录后继续跑其余 group
            group_summaries.append({"group_id": group.group_id, "status": "ERROR", "error": str(exc)})
        finally:
            report = cleanup.finally_cleanup(
                tracked_pgids=tracked_pgids,
                workspace_path=ws,
                workspaces_root=workspaces_root,
                fixture_dir=fixture_dir,
                fixture_expected_hash=fixture_hash,
            )
            cleanup_dir = artifacts_root / run_id / exp_id / "_cleanup"
            cleanup_dir.mkdir(parents=True, exist_ok=True)
            artifacts.write_json(cleanup_dir / f"{group.group_id}.json", dataclasses.asdict(report))

    vertical_by_step = {
        f"{group_id}/{step_id}": stability.evaluate_vertical(raws, rules)
        for (group_id, step_id), raws in results_by_group_step.items()
    }

    horizontal_by_group = {}
    if spec.analysis.type == "stability":
        for command, raws_by_group in _group_common_command_at_warm(spec, results_by_group_step).items():
            horizontal_by_group[command] = stability.evaluate_horizontal(raws_by_group, rules)

    evaluation = analyzer_base.dispatch(
        spec.analysis.type,
        vertical_by_step=vertical_by_step,
        horizontal_by_group=horizontal_by_group,
    )

    exp_artifact_dir = artifacts_root / run_id / exp_id
    exp_artifact_dir.mkdir(parents=True, exist_ok=True)
    artifacts.write_json(exp_artifact_dir / "evaluation.json", dataclasses.asdict(evaluation))
    artifacts.write_json(exp_artifact_dir / "groups.json", group_summaries)

    return {
        "exp_id": exp_id,
        "run_id": run_id,
        "groups": group_summaries,
        "evaluation": dataclasses.asdict(evaluation),
    }
