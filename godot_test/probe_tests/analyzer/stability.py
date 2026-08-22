#!/usr/bin/env python3
"""analyzer/stability.py —— 纵向重复差异（stabilizer）。

用法：
    python analyzer/stability.py artifacts/<run-id>
    python analyzer/stability.py artifacts/<run-id>/N09/
    python analyzer/stability.py artifacts/<run-id>/N09/ --out reports/<run-id>/N09/stability/

输入可以是一次 run 的根目录（其下有 N09/ 等实验目录），也可以是单个实验目录。
每个实验写出：
    reports/<run-id>/<N>/stability/stability.json

每个 step = (project / group, cmd V, cache_state)。COLD 与 WARM 是两个 step。
对每个 step 的全部 repeat，比较 stdout + stderr：
    line_set_identical              行集合是否逐次相同
    common_line_order_identical     去掉非公共行后，公共行出现顺序是否一致

只读磁盘，不修改 artifacts/，不启动 Godot，不写 CONFIRMED。
横向跨项目行差不在本脚本；本文件只做纵向 stabilizer。

禁止：import 实验脚本；修改 artifacts/；写死 fixture 名。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

PROBE_ROOT = Path(__file__).resolve().parents[1]
CACHE_STATES = ("COLD", "WARM", "PRESERVE")
STREAMS = ("stdout", "stderr")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    artifact_root = _resolve_existing(args.artifact_dir)
    experiment_dirs = _discover_experiment_dirs(artifact_root)
    if not experiment_dirs:
        sys.stderr.write(
            f"no experiment directory with group/step/cache/repeat logs under {artifact_root}\n"
        )
        return 2

    written: list[Path] = []
    for exp_dir in experiment_dirs:
        report = analyze_experiment(exp_dir)
        out_dir = _default_out_dir(exp_dir) if args.out is None else Path(args.out)
        if args.out is not None and len(experiment_dirs) > 1:
            out_dir = Path(args.out) / report["N"] / "stability"
        out_dir = out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / "stability.json"
        dest.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(dest)

    for path in written:
        sys.stdout.write(f"{path}\n")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Longitudinal stabilizer: compare stdout/stderr across repeats of each step."
    )
    parser.add_argument(
        "artifact_dir",
        help="artifacts/<run-id> or artifacts/<run-id>/<N>",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="output directory (default: reports/<run-id>/<N>/stability/)",
    )
    return parser.parse_args(argv)


def analyze_experiment(experiment_dir: Path) -> dict[str, Any]:
    measurements = list(_iter_measurements(experiment_dir))
    if not measurements:
        raise SystemExit(f"no measurements under {experiment_dir}")

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in measurements:
        key = (item["group_id"], item["cmd"], item["cache_state"])
        grouped[key].append(item)

    steps: list[dict[str, Any]] = []
    for key in sorted(grouped, key=_step_sort_key):
        repeats = sorted(grouped[key], key=lambda m: int(m["repeat_idx"]))
        steps.append(_analyze_step(repeats))

    sample = measurements[0]
    unstable = [
        s
        for s in steps
        if not s["line_set_identical"] or not s["common_line_order_identical"]
    ]
    return {
        "analyzer": "stability",
        "view": "longitudinal",
        "run_id": sample.get("run_id"),
        "N": sample.get("N"),
        "artifact_dir": str(experiment_dir),
        "inputs_digest": sample.get("inputs_digest"),
        "step_count": len(steps),
        "repeat_total": len(measurements),
        "all_line_sets_identical": all(s["line_set_identical"] for s in steps),
        "all_common_line_orders_identical": all(
            s["common_line_order_identical"] for s in steps
        ),
        "unstable_step_count": len(unstable),
        "steps": steps,
    }


def _analyze_step(repeats: list[dict[str, Any]]) -> dict[str, Any]:
    first = repeats[0]
    by_stream = {
        stream: [m["lines"][stream] for m in repeats] for stream in STREAMS
    }
    combined = [
        [f"{stream}: {line}" for stream in STREAMS for line in m["lines"][stream]]
        for m in repeats
    ]

    combined_cmp = _compare_line_lists(combined)
    stream_cmp = {
        stream: _compare_line_lists(by_stream[stream]) for stream in STREAMS
    }

    record: dict[str, Any] = {
        "project": first["group_id"],
        "fixture": first.get("fixture"),
        "cmd": first["cmd"],
        "cache_state": first["cache_state"],
        "step_id": first.get("step_id"),
        "target": first.get("target"),
        "repeat_count": len(repeats),
        "repeat_indices": [int(m["repeat_idx"]) for m in repeats],
        "line_set_identical": combined_cmp["line_set_identical"],
        "common_line_order_identical": combined_cmp["common_line_order_identical"],
        "streams": {},
    }
    for stream in STREAMS:
        record["streams"][stream] = _stream_view(
            stream_cmp[stream],
            by_stream[stream],
            [int(m["repeat_idx"]) for m in repeats],
        )
    if not combined_cmp["line_set_identical"]:
        record["jitter_lines"] = _jitter_lines(
            combined,
            [int(m["repeat_idx"]) for m in repeats],
        )
    if (
        not combined_cmp["common_line_order_identical"]
        and combined_cmp["common_order_by_repeat"]
    ):
        record["common_order_by_repeat"] = {
            str(idx): seq
            for idx, seq in zip(
                [int(m["repeat_idx"]) for m in repeats],
                combined_cmp["common_order_by_repeat"],
            )
        }
    return record


def _stream_view(
    cmp: dict[str, Any],
    line_lists: list[list[str]],
    repeat_indices: list[int],
) -> dict[str, Any]:
    view: dict[str, Any] = {
        "line_set_identical": cmp["line_set_identical"],
        "common_line_order_identical": cmp["common_line_order_identical"],
        "line_count_by_repeat": {
            str(idx): len(lines) for idx, lines in zip(repeat_indices, line_lists)
        },
        "union_size": cmp["union_size"],
        "intersection_size": cmp["intersection_size"],
    }
    if not cmp["line_set_identical"]:
        view["jitter_lines"] = _jitter_lines(line_lists, repeat_indices)
    if not cmp["common_line_order_identical"] and cmp["common_order_by_repeat"]:
        view["common_order_by_repeat"] = {
            str(idx): seq
            for idx, seq in zip(repeat_indices, cmp["common_order_by_repeat"])
        }
    return view


def _compare_line_lists(line_lists: list[list[str]]) -> dict[str, Any]:
    sets = [set(lines) for lines in line_lists]
    if not sets:
        return {
            "line_set_identical": True,
            "common_line_order_identical": True,
            "union_size": 0,
            "intersection_size": 0,
            "common_order_by_repeat": [],
        }

    union: set[str] = set().union(*sets) if sets else set()
    intersection: set[str] = set.intersection(*sets) if sets else set()
    line_set_identical = all(s == sets[0] for s in sets)

    filtered = [[line for line in lines if line in intersection] for lines in line_lists]
    common_line_order_identical = all(seq == filtered[0] for seq in filtered)
    return {
        "line_set_identical": line_set_identical,
        "common_line_order_identical": common_line_order_identical,
        "union_size": len(union),
        "intersection_size": len(intersection),
        "common_order_by_repeat": filtered,
    }


def _jitter_lines(
    line_lists: list[list[str]],
    repeat_indices: list[int],
) -> list[dict[str, Any]]:
    sets = [set(lines) for lines in line_lists]
    intersection = set.intersection(*sets) if sets else set()
    union = set().union(*sets) if sets else set()
    jitter: list[dict[str, Any]] = []
    for line in sorted(union - intersection):
        present = [
            idx for idx, s in zip(repeat_indices, sets) if line in s
        ]
        absent = [
            idx for idx, s in zip(repeat_indices, sets) if line not in s
        ]
        jitter.append(
            {
                "line": line,
                "present_in": present,
                "absent_in": absent,
            }
        )
    return jitter


def _iter_measurements(experiment_dir: Path) -> Iterable[dict[str, Any]]:
    for meta_path in sorted(experiment_dir.rglob("metadata.json")):
        repeat_dir = meta_path.parent
        cache_state = repeat_dir.parent.name
        if cache_state not in CACHE_STATES:
            continue
        if not (repeat_dir / "stdout.log").exists() and not (
            repeat_dir / "stderr.log"
        ).exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(meta, dict):
            continue
        group_id = meta.get("group_id") or repeat_dir.parent.parent.parent.name
        step_id = meta.get("step_id") or repeat_dir.parent.parent.name
        cmd = meta.get("cmd") or _cmd_from_step(step_id)
        try:
            repeat_idx = int(meta.get("repeat_idx", repeat_dir.name))
        except (TypeError, ValueError):
            continue
        yield {
            "N": meta.get("N") or experiment_dir.name,
            "run_id": meta.get("run_id") or experiment_dir.parent.name,
            "group_id": group_id,
            "step_id": step_id,
            "cache_state": meta.get("cache_state") or cache_state,
            "repeat_idx": repeat_idx,
            "cmd": cmd,
            "target": meta.get("target"),
            "fixture": meta.get("fixture"),
            "inputs_digest": meta.get("inputs_digest"),
            "dir": repeat_dir,
            "lines": {
                "stdout": _read_log_lines(repeat_dir / "stdout.log"),
                "stderr": _read_log_lines(repeat_dir / "stderr.log"),
            },
        }


def _read_log_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text == "":
        return []
    if text.endswith("\n"):
        text = text[:-1]
    return text.split("\n")


def _discover_experiment_dirs(path: Path) -> list[Path]:
    if _looks_like_experiment_dir(path):
        return [path]
    found: list[Path] = []
    for child in sorted(path.iterdir() if path.is_dir() else []):
        if child.is_dir() and _looks_like_experiment_dir(child):
            found.append(child)
    return found


def _looks_like_experiment_dir(path: Path) -> bool:
    """实验目录的测量落在 group/step/cache/repeat/，不能把 run-id 根目录算进去。"""
    if not path.is_dir():
        return False
    if (path / "index.md").is_file() or (path / "run.json").is_file():
        return True
    for meta in path.glob("*/*/*/*/metadata.json"):
        if meta.parent.parent.name in CACHE_STATES:
            return True
    return False


def _default_out_dir(experiment_dir: Path) -> Path:
    experiment_dir = experiment_dir.resolve()
    artifacts_dir = PROBE_ROOT / "artifacts"
    try:
        rel = experiment_dir.relative_to(artifacts_dir)
        return PROBE_ROOT / "reports" / rel / "stability"
    except ValueError:
        return experiment_dir / "stability"


def _resolve_existing(raw: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute():
        cwd_try = (Path.cwd() / candidate).resolve()
        if cwd_try.exists():
            return cwd_try
        root_try = (PROBE_ROOT / candidate).resolve()
        if root_try.exists():
            return root_try
        return cwd_try
    resolved = candidate.resolve()
    if not resolved.exists():
        raise SystemExit(f"artifact path does not exist: {resolved}")
    return resolved


def _cmd_from_step(step_id: str) -> str:
    token = step_id.split("-", 1)[0]
    if token.lower().startswith("v") and token[1:].isdigit():
        return token.upper()
    return step_id


def _step_sort_key(key: tuple[str, str, str]) -> tuple[str, str, int, str]:
    project, cmd, cache = key
    cache_rank = {name: i for i, name in enumerate(CACHE_STATES)}
    return (project, cmd, cache_rank.get(cache, 99), cache)


if __name__ == "__main__":
    sys.exit(main())
