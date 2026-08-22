"""YAML schema 加载与校验。

ExperimentSpec = 一个 N。每个 N 由若干 group 组成，每个 group 对应一次
"从 fixture 独立 clone 一个 workspace"（决策：多子实验各自独立 clone，不做
"同一 workspace 内恢复"——N01 的 shadow_config / res_loader 分支就是同一个
fixture 下的两个 group）。group 内的 steps 严格有序，共享同一个 workspace，
是状态的自然演进（COLD -> WARM -> ...），不是"恢复"。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from .types import CacheState


class SchemaError(Exception):
    pass


@dataclass
class HookSpec:
    name: str
    args: dict = field(default_factory=dict)


@dataclass
class StepSpec:
    step_id: str
    command: str
    cache_state: CacheState
    repeat: int
    timeout_seconds: float
    hooks: list[HookSpec] = field(default_factory=list)
    capture: list[str] = field(default_factory=list)
    script: Optional[str] = None
    extra_flags: list[str] = field(default_factory=list)


@dataclass
class GroupSpec:
    group_id: str
    fixture: str
    steps: list[StepSpec] = field(default_factory=list)
    derived: Optional[str] = None


@dataclass
class AnalysisSpec:
    """YAML 的判定选型。仅 Analyzer.py / 事后脚本读取；kernel 忽略。"""

    type: str
    extra: dict = field(default_factory=dict)


@dataclass
class ExperimentSpec:
    id: str
    phase: str
    analysis: AnalysisSpec
    groups: list[GroupSpec] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    engine_profile: dict = field(default_factory=dict)
    manual_gates: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    repeat_default: int = 3
    timeout_default: float = 30.0


def _require(mapping: dict, key: str, ctx: str) -> Any:
    if key not in mapping:
        raise SchemaError(f"{ctx}: 缺少必填字段 {key!r}")
    return mapping[key]


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise SchemaError(f"{path}: 顶层内容必须是 mapping")
    return data


def _merge_defaults(spec: dict, defaults: dict) -> dict:
    merged = dict(defaults)
    merged.update(spec)
    return merged


def validate_steps_ordered(raw_steps: Any, ctx: str) -> list[dict]:
    if isinstance(raw_steps, dict):
        raise SchemaError(
            f"{ctx}: steps 必须是有序 list，禁止矩阵式 dict/mapping 写法"
        )
    if not isinstance(raw_steps, list):
        raise SchemaError(f"{ctx}: steps 必须是 list")
    seen_ids = set()
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            raise SchemaError(f"{ctx}: 每个 step 必须是 mapping")
        step_id = raw_step.get("step_id")
        if not step_id:
            raise SchemaError(f"{ctx}: step 缺少 step_id")
        if step_id in seen_ids:
            raise SchemaError(f"{ctx}: step_id 重复: {step_id}")
        seen_ids.add(step_id)
    return raw_steps


def _parse_step(raw: dict, ctx: str, repeat_default: int, timeout_default: float) -> StepSpec:
    hooks = [HookSpec(name=h["name"], args=h.get("args", {})) for h in raw.get("hooks", [])]
    cache_state_raw = _require(raw, "cache_state", ctx)
    try:
        cache_state = CacheState(cache_state_raw)
    except ValueError as exc:
        raise SchemaError(f"{ctx}: 非法 cache_state {cache_state_raw!r}") from exc
    return StepSpec(
        step_id=raw["step_id"],
        command=_require(raw, "command", ctx),
        cache_state=cache_state,
        repeat=int(raw.get("repeat", repeat_default)),
        timeout_seconds=float(raw.get("timeout_seconds", timeout_default)),
        hooks=hooks,
        capture=list(raw.get("capture", [])),
        script=raw.get("script"),
        extra_flags=list(raw.get("extra_flags", [])),
    )


def _parse_group(raw: dict, ctx: str, repeat_default: int, timeout_default: float) -> GroupSpec:
    group_id = _require(raw, "group_id", ctx)
    fixture = _require(raw, "fixture", ctx)
    raw_steps = validate_steps_ordered(_require(raw, "steps", ctx), f"{ctx}/{group_id}")
    steps = [
        _parse_step(raw_step, f"{ctx}/{group_id}/{raw_step.get('step_id')}", repeat_default, timeout_default)
        for raw_step in raw_steps
    ]
    return GroupSpec(group_id=group_id, fixture=fixture, steps=steps, derived=raw.get("derived"))


def find_experiment_yaml(experiments_root: Path, exp_id: str) -> Path:
    experiments_root = Path(experiments_root)
    if experiments_root.is_dir():
        for phase_dir in sorted(p for p in experiments_root.iterdir() if p.is_dir()):
            candidate = phase_dir / f"{exp_id}.yaml"
            if candidate.is_file():
                return candidate
    raise FileNotFoundError(f"找不到实验 YAML: {exp_id} (searched under {experiments_root})")


def load_experiment(path: Path, common_dir: Optional[Path] = None) -> ExperimentSpec:
    """解析单个 N 的 YAML，与 experiments/common/defaults.yaml 浅合并。"""
    raw = _load_yaml(path)
    defaults: dict = {}
    if common_dir is not None:
        defaults_path = Path(common_dir) / "defaults.yaml"
        if defaults_path.exists():
            defaults = _load_yaml(defaults_path)
    merged = _merge_defaults(raw, {k: v for k, v in defaults.items() if k not in ("id", "phase")})

    exp_id = _require(merged, "id", str(path))
    ctx = f"{path}[{exp_id}]"
    phase = _require(merged, "phase", ctx)

    analysis_raw = _require(merged, "analysis", ctx)
    analysis = AnalysisSpec(type=_require(analysis_raw, "type", ctx), extra=analysis_raw.get("extra", {}))

    repeat_default = int(merged.get("repeat", 3))
    timeout_default = float(merged.get("timeout_seconds", 30.0))

    raw_groups = _require(merged, "groups", ctx)
    if not isinstance(raw_groups, list):
        raise SchemaError(f"{ctx}: groups 必须是 list")
    groups = [_parse_group(g, ctx, repeat_default, timeout_default) for g in raw_groups]

    engine_profile_raw = merged.get("engine_profile", {})
    if common_dir is not None and not engine_profile_raw:
        defaults_engine = defaults.get("engine_profile", {})
        engine_profile_raw = defaults_engine

    return ExperimentSpec(
        id=exp_id,
        phase=phase,
        analysis=analysis,
        groups=groups,
        depends_on=list(merged.get("depends_on", [])),
        engine_profile=engine_profile_raw,
        manual_gates=list(merged.get("manual_gates", [])),
        exports=list(merged.get("exports", [])),
        repeat_default=repeat_default,
        timeout_default=timeout_default,
    )
