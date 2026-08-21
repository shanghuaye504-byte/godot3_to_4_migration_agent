"""实验导演：把 YAML 展开成多次 capture.run_measurement，并负责跨步骤状态。

本模块是 kernel 里唯一允许「记住上一拍」的地方（例如 V3 成功 → 后面可以 WARM）。
它不 Popen Godot；每次真正跑命令都委托 capture.run_measurement。

阶段（对一个 N，如 N09）：

  A. 开场
     schema.load_experiment     读 YAML
     digest / engine_profile    盖输入指纹、确认 Godot 或 Fake
     check_freshness            MISSING 拒跑；STALE 默认拒，--force-stale 才跑
     （Fake 不读写 artifacts/latest/）

  B. 每个 group（独立 workspace，对应四元组的 project）
     workspace.create + git_init
     digest.compute_inputs_digest   本 group 的 inputs_digest
     对每个 step（有序，对应「做哪件不同的事」）：
       cache.resolve_cache_state    COLD 删 .godot / WARM 检查标记
       _run_step_repeats：
         对每个 repeat_idx（同一件事再拍一遍）：
           hooks.apply              例如 V9 写入哨兵
           commands.resolve         V3 → argv 列表
           构造 Measurement 标签
           capture.run_measurement  ← 唯一按快门的地方
           hooks.revoke             删掉哨兵
         artifacts.write_*          把每条 RawResult 写成 log
       若本 step 是成功的 V3 → cache.mark_warm
     finally cleanup                无论成败：杀进程组、删 workspace、验 fixture

  C. 收工
     analyzer（stability）吃全部 RawResult，写 evaluation.json
     （判定不是 kernel 的职责，但当前由导演在片尾喊一声「去剪辑」）

和 capture 的边界：
  runner  = 拍什么、以什么顺序、拍几遍、布景/收工
  capture = 按下快门，交回一条 RawResult
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
    profile = EngineProfile(
        executable=executable,
        version=raw.get("version", ""),
        build_hash=raw.get("build_hash", ""),
        fake=bool(raw.get("fake", False)),
    )
    if not profile.build_hash:
        profile = EngineProfile(
            executable=profile.executable,
            version=profile.version,
            build_hash=digest.compute_build_hash(profile),
            fake=profile.fake,
        )
    return profile


def _annotation_path(annotations_root: Path, fixture: str) -> Path:
    return Path(annotations_root) / f"{fixture}.yaml"


def _group_inputs_digest(
    *,
    fixture_hash: str,
    annotations_root: Path,
    fixture: str,
    derived: Optional[str],
    engine_profile: EngineProfile,
) -> str:
    annotation_file = _annotation_path(annotations_root, fixture)
    annotation_hash = digest.compute_file_hash(annotation_file) if annotation_file.is_file() else ""
    derived_patch_hash = None
    if derived:
        patch_file = PROBE_ROOT / "derived" / derived / "patch.diff"
        if patch_file.is_file():
            derived_patch_hash = digest.compute_file_hash(patch_file)
    return digest.compute_inputs_digest(
        digest.DigestComponents(
            fixture_hash=fixture_hash,
            annotation_hash=annotation_hash,
            derived_patch_hash=derived_patch_hash,
            build_hash=engine_profile.build_hash,
        )
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
    inputs_digest: str,
) -> list:
    """一个 step 的内层循环：repeat 次调用 capture.run_measurement。

    每次 repeat 现场相同（同一 argv 模板、同一 cache_state），只改 repeat_idx。
    全部 repeat 收齐后再落盘，便于纵向 evaluation 写进每条 artifact。
    """
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
                inputs_digest=inputs_digest,
            )
            tracked_pgids.append(raw.process.pgid)
            raws.append(raw)
        finally:
            hook_registry.revoke_hooks(invocations)

    vertical_eval = stability.evaluate_vertical(raws, rules)
    for repeat_idx, raw in enumerate(raws):
        directory = artifacts.step_artifact_dir(
            artifacts_root,
            run_id,
            exp_id,
            group.group_id,
            step.step_id,
            step.cache_state.value,
            repeat_idx,
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
    annotations_root: Optional[Path] = None,
    fake: bool = False,
    repeat_override: Optional[int] = None,
    force_stale: bool = False,
) -> dict:
    experiments_root = Path(experiments_root or PROBE_ROOT / "experiments")
    common_dir = Path(common_dir or experiments_root / "common")
    fixtures_root = Path(fixtures_root or PROBE_ROOT / "fixtures")
    workspaces_root = Path(workspaces_root or PROBE_ROOT / "workspaces")
    artifacts_root = Path(artifacts_root or PROBE_ROOT / "artifacts")
    annotations_root = Path(annotations_root or PROBE_ROOT / "annotations")

    spec_path = _find_experiment_yaml(experiments_root, exp_id)
    spec = schema.load_experiment(spec_path, common_dir=common_dir)

    engine_raw = dict(spec.engine_profile)
    if fake:
        from ..testing import fake_godot

        engine_raw["executable"] = fake_godot.executable_argv()
        engine_raw["fake"] = True
        version = engine_raw.get("version") or "4.7.1.stable.official"
        if not str(version).endswith(".fake"):
            engine_raw["version"] = f"{version}.fake"
        engine_raw["build_hash"] = ""

    engine_profile = _resolve_engine_profile(engine_raw)
    if repeat_override is not None:
        for group in spec.groups:
            for step in group.steps:
                step.repeat = int(repeat_override)

    group_previews = []
    for group in spec.groups:
        fixture_dir = fixtures_root / group.fixture
        fixture_hash = digest.compute_tree_hash(fixture_dir)
        group_digest = _group_inputs_digest(
            fixture_hash=fixture_hash,
            annotations_root=annotations_root,
            fixture=group.fixture,
            derived=group.derived,
            engine_profile=engine_profile,
        )
        group_previews.append(
            {
                "group": group,
                "fixture_dir": fixture_dir,
                "fixture_hash": fixture_hash,
                "inputs_digest": group_digest,
            }
        )

    upstream_export_paths = {
        name: digest.latest_record_path(artifacts_root, name) for name in spec.depends_on
    }
    upstream_export_hashes = {
        name: digest.compute_file_hash(path)
        for name, path in upstream_export_paths.items()
        if path.is_file()
    }
    experiment_digest = digest.compute_experiment_digest(
        {item["group"].group_id: item["inputs_digest"] for item in group_previews},
        upstream_export_hashes,
    )

    if fake:
        freshness = digest.FreshnessResult(
            status="FRESH",
            reason="fake run skips artifacts/latest gate",
            digest=experiment_digest,
        )
    else:
        freshness = digest.check_freshness(
            spec.depends_on,
            upstream_export_paths,
            experiment_digest,
            recorded_digest_path=digest.latest_record_path(artifacts_root, exp_id),
        )
        if freshness.status in ("MISSING", "BLOCKED"):
            raise digest.BlockedExperimentError(freshness.reason)
        if freshness.status == "STALE" and not force_stale:
            raise digest.BlockedExperimentError(freshness.reason)

    profiles = commands.load_command_profiles(common_dir)
    rules = normalize.load_signature_rules(common_dir / "signature-rules.yaml")

    results_by_group_step: dict = {}
    group_summaries = []

    for preview in group_previews:
        group = preview["group"]
        fixture_dir = preview["fixture_dir"]
        fixture_hash = preview["fixture_hash"]
        inputs_digest = preview["inputs_digest"]
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
                    inputs_digest=inputs_digest,
                )
                results_by_group_step[(group.group_id, step.step_id)] = raws
                if step.command in _WARM_TRIGGER_COMMANDS and _last_success(raws):
                    cache.mark_warm(ws, step.step_id)

            group_summaries.append(
                {"group_id": group.group_id, "status": "OK", "inputs_digest": inputs_digest}
            )
        except Exception as exc:  # noqa: BLE001 - 记录后继续跑其余 group
            group_summaries.append(
                {
                    "group_id": group.group_id,
                    "status": "ERROR",
                    "error": str(exc),
                    "inputs_digest": inputs_digest,
                }
            )
        finally:
            report = cleanup.finally_cleanup(
                tracked_pgids=tracked_pgids,
                workspace_path=ws,
                workspaces_root=workspaces_root,
                fixture_dir=fixture_dir,
                fixture_expected_hash=fixture_hash,
            )
            group_dir = artifacts_root / run_id / exp_id / group.group_id
            group_dir.mkdir(parents=True, exist_ok=True)
            artifacts.write_cleanup(group_dir, dataclasses.asdict(report))

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

    all_groups_ok = bool(group_summaries) and all(item.get("status") == "OK" for item in group_summaries)
    latest_path = None
    if all_groups_ok and not engine_profile.fake:
        latest_path = artifacts.write_latest_record(
            artifacts_root,
            exp_id=exp_id,
            run_id=run_id,
            inputs_digest=experiment_digest,
            groups=group_summaries,
            engine_profile=dataclasses.asdict(engine_profile),
        )

    return {
        "exp_id": exp_id,
        "run_id": run_id,
        "fake": engine_profile.fake,
        "engine_profile": dataclasses.asdict(engine_profile),
        "artifacts_root": str(artifacts_root / run_id),
        "groups": group_summaries,
        "evaluation": dataclasses.asdict(evaluation),
        "freshness": dataclasses.asdict(freshness),
        "experiment_digest": experiment_digest,
        "force_stale": force_stale,
        "latest_record": str(latest_path) if latest_path else None,
    }
