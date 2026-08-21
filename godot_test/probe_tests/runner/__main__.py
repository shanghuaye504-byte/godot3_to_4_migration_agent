"""CLI 入口：python -m runner <experiment-id> [--run-id ID]

规划职责：解析命令行、加载 experiments/**/*.yaml、调度 kernel、分派 analyzer、
触发 report。当前只接入 kernel.runner.run_experiment（本轮范围：让 N09 能跑）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from .kernel import runner as kernel_runner


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m runner")
    parser.add_argument("experiment_id")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)

    run_id = args.run_id or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    result = kernel_runner.run_experiment(args.experiment_id, run_id=run_id)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
