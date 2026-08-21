"""CLI 入口：python -m runner <experiment-id> [--run-id ID] [--fake] [--repeat N] [--force-stale]

解析命令行、加载 experiments/**/*.yaml、调度 kernel、分派 analyzer、
写出 artifacts/<run-id>/index.md。
STALE 默认拒绝；--force-stale 仅绕过 STALE，不能绕过 MISSING。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .kernel import digest, runner as kernel_runner
from .report import index as report_index

PROBE_ROOT = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m runner")
    parser.add_argument("experiment_id")
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--fake",
        action="store_true",
        help="使用 Fake Godot；产物不得作为已确认结论，且不更新 artifacts/latest/",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=None,
        help="覆盖 YAML 中的 repeat（kernel 冒烟可设为 1）",
    )
    parser.add_argument(
        "--force-stale",
        action="store_true",
        help="配方已变仍重跑本实验（仅绕过 STALE；MISSING 仍拒绝）",
    )
    args = parser.parse_args(argv)

    run_id = args.run_id or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    try:
        result = kernel_runner.run_experiment(
            args.experiment_id,
            run_id=run_id,
            fake=args.fake,
            repeat_override=args.repeat,
            force_stale=args.force_stale,
        )
    except digest.BlockedExperimentError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    artifacts_root = Path(result.get("artifacts_root") or (PROBE_ROOT / "artifacts" / run_id))
    index_path = report_index.write_run_index(artifacts_root, run_id=run_id, summary=result)
    result["index_md"] = str(index_path)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
