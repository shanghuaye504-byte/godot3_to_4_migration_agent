#!/usr/bin/env python3
"""事后判定入口。

    python Analyzer.py --path artifacts/<run-id>/<N>/

只读已落盘的 log / diff / metadata，不启动 Godot，不碰 workspace。
analysis.type 从 experiments/<phase>/<N>.yaml 读取（可用 --type 覆盖）。
kernel / python -m runner 不调用本文件。
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

PROBE_ROOT = Path(__file__).resolve().parent
if str(PROBE_ROOT) not in sys.path:
    sys.path.insert(0, str(PROBE_ROOT))

from runner.analyzers import base as analyzer_base  # noqa: E402
from runner.analyzers import stability  # noqa: F401,E402
from runner.kernel import artifacts, schema  # noqa: E402


def _looks_like_exp_dir(path: Path) -> bool:
    if (path / "groups.json").is_file():
        return True
    return any(True for _ in artifacts.iter_step_dirs(path))


def resolve_exp_dir(path: Path) -> Path:
    path = Path(path).resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"--path 不是目录: {path}")
    if _looks_like_exp_dir(path):
        return path
    children = sorted(
        p for p in path.iterdir() if p.is_dir() and not p.name.startswith(".")
    )
    exp_children = [p for p in children if _looks_like_exp_dir(p)]
    if len(exp_children) == 1:
        return exp_children[0]
    names = ", ".join(p.name for p in exp_children) or "（无）"
    raise FileNotFoundError(
        f"--path 应指向 artifacts/<run-id>/<N>/（含 groups.json 或测量目录）。"
        f" 当前 {path} 下匹配到: {names}"
    )


def _is_fake(exp_dir: Path) -> bool:
    for _group_id, repeat_dir in artifacts.iter_step_dirs(exp_dir):
        meta_path = repeat_dir / "metadata.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if bool((meta.get("engine_profile") or {}).get("fake")):
            return True
    return False


def _analysis_type_and_phase(exp_id: str, type_override: str | None) -> tuple[str, str]:
    yaml_path = schema.find_experiment_yaml(PROBE_ROOT / "experiments", exp_id)
    spec = schema.load_experiment(yaml_path, common_dir=PROBE_ROOT / "experiments" / "common")
    analysis_type = type_override or spec.analysis.type
    return analysis_type, spec.phase


def run(path: Path, *, type_override: str | None = None, out_dir: Path | None = None) -> dict:
    exp_dir = resolve_exp_dir(path)
    exp_id = exp_dir.name
    run_dir = exp_dir.parent
    run_id = run_dir.name
    analysis_type, phase = _analysis_type_and_phase(exp_id, type_override)
    shots = artifacts.load_exp_shots(exp_dir)
    fake = _is_fake(exp_dir)
    dest = Path(out_dir) if out_dir else (PROBE_ROOT / "report" / phase / exp_id)
    evaluation = analyzer_base.dispatch(
        analysis_type,
        shots=shots,
        out_dir=dest,
        run_id=run_id,
        run_dir=run_dir,
        fake=fake,
    )
    if evaluation.status == "NOT_IMPLEMENTED":
        dest.mkdir(parents=True, exist_ok=True)
        artifacts.write_json(dest / "dispatch.json", dataclasses.asdict(evaluation))
    return {
        "exp_id": exp_id,
        "phase": phase,
        "run_id": run_id,
        "path": str(exp_dir),
        "analysis_type": analysis_type,
        "fake": fake,
        "shots": len(shots),
        "report_dir": str(dest),
        "evaluation": dataclasses.asdict(evaluation),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python Analyzer.py")
    parser.add_argument(
        "--path",
        required=True,
        help="artifacts/<run-id>/<N>/（也可指向只含一个 N 的 artifacts/<run-id>/）",
    )
    parser.add_argument(
        "--type",
        default=None,
        help="覆盖 YAML 的 analysis.type（事后脚本选型时用）",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="默认 report/<phase>/<N>/",
    )
    args = parser.parse_args(argv)
    try:
        result = run(
            Path(args.path),
            type_override=args.type,
            out_dir=Path(args.out_dir) if args.out_dir else None,
        )
    except (FileNotFoundError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
