#!/usr/bin/env python3
"""analyzer/exitcode.py —— rc / signal / timeout 交叉表，含存活性观测。

用法：
    python analyzer/exitcode.py artifacts/<run-id>
    python analyzer/exitcode.py artifacts/<run-id>/N08/
    python analyzer/exitcode.py artifacts/<run-id>/N08/ --out reports/<run-id>/N08/exitcode/

每个 step 汇总多次 repeat 的 rc / signal / timed_out：
    全部相同 → 该字段的最终答案就是这个值
    出现分歧 → anomaly=true，value 为 null，并列出各 repeat 的值

本脚本填表，不宣布 exit_code 可否当 success，不写 CONFIRMED。
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
CRASH_MARK = "handle_crash: Program crashed with signal 11"
CONSENSUS_FIELDS = ("rc", "signal", "timed_out")

# 交叉表用 group/cmd/cache 对齐步骤表，不打开 fixture、不写死 fixture 路径。
CROSS_ROWS = (
    {
        "id": "clean",
        "scene": "干净",
        "has_real_error": False,
        "expected_rc": "0",
        "match": {"group_id": "clean-control", "cmd": "V1", "cache_state": "WARM"},
    },
    {
        "id": "file-true-error",
        "scene": "单文件真错",
        "has_real_error": True,
        "expected_rc": "≠0",
        "match": {"group_id": "np-syntax", "cmd": "V2", "cache_state": "WARM"},
    },
    {
        "id": "project-true-error",
        "scene": "项目级真错",
        "has_real_error": True,
        "expected_rc": "≠0",
        "match": {"group_id": "np-syntax", "cmd": "V1", "cache_state": "WARM"},
    },
    {
        "id": "false-positive-candidate",
        "scene": "纯假阳性候选",
        "has_real_error": None,
        "expected_rc": "0",
        "match": {"group_id": "np-autoload", "cmd": "V2", "cache_state": "COLD"},
        "note": "「有真错误＝否」由 N01 确认后回填，本脚本不预判",
    },
    {
        "id": "v8-timeout-kill",
        "scene": "被 timeout kill",
        "has_real_error": None,
        "expected_rc": "124/137",
        "match": {"cmd": "V8"},
        "note": "V8 可能有 NP-SYNTAX 与 NP-ADDON 两格，都列出",
    },
)


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
            out_dir = Path(args.out) / report["N"] / "exitcode"
        out_dir = out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / "exitcode.json"
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
        description="Exit-code analyzer: consensus of rc/signal/timeout across repeats."
    )
    parser.add_argument(
        "artifact_dir",
        help="artifacts/<run-id> or artifacts/<run-id>/<N>",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="output directory (default: reports/<run-id>/<N>/exitcode/)",
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
    anomaly_steps = [s for s in steps if s["anomaly"]]
    return {
        "_comment": (
            "每个 step 的 rc / signal / timed_out：repeats 全部相同则 value 就是最终答案；"
            "不一致则 anomaly=true、value=null。本文件是中间结果，不是 CONFIRMED。"
        ),
        "analyzer": "exitcode",
        "run_id": sample.get("run_id"),
        "N": sample.get("N"),
        "artifact_dir": str(experiment_dir),
        "inputs_digest": sample.get("inputs_digest"),
        "step_count": len(steps),
        "repeat_total": len(measurements),
        "all_repeats_consistent": not anomaly_steps,
        "anomaly_step_count": len(anomaly_steps),
        "steps": steps,
        "cross_table": _cross_table(steps),
        "b9": _b9(steps),
        "v8_liveness": _v8_liveness(steps),
    }


def _analyze_step(repeats: list[dict[str, Any]]) -> dict[str, Any]:
    first = repeats[0]
    fields = {name: _consensus([m["status"][name] for m in repeats], repeats) for name in CONSENSUS_FIELDS}
    anomaly = any(not fields[name]["consistent"] for name in CONSENSUS_FIELDS)
    record: dict[str, Any] = {
        "project": first["group_id"],
        "fixture": first.get("fixture"),
        "cmd": first["cmd"],
        "cache_state": first["cache_state"],
        "step_id": first.get("step_id"),
        "target": first.get("target"),
        "repeat_count": len(repeats),
        "repeat_indices": [int(m["repeat_idx"]) for m in repeats],
        "timeout_seconds": first.get("timeout_seconds"),
        "rc": fields["rc"],
        "signal": fields["signal"],
        "timed_out": fields["timed_out"],
        "wall_time_by_repeat": {
            str(m["repeat_idx"]): m["status"].get("wall_time") for m in repeats
        },
        "anomaly": anomaly,
    }
    if anomaly:
        record["anomaly_fields"] = [
            name for name in CONSENSUS_FIELDS if not fields[name]["consistent"]
        ]
        record["_comment"] = "本 step 多次 repeat 的 rc/signal/timed_out 不一致，value 不能当最终答案。"
    extras = [m.get("leftover") for m in repeats if m.get("leftover") is not None]
    if extras:
        record["leftover_godot"] = extras
    crash_hits = [int(m["repeat_idx"]) for m in repeats if m.get("crash_mark")]
    if crash_hits:
        record["crash_mark_in_stderr_repeats"] = crash_hits
    return record


def _consensus(values: list[Any], repeats: list[dict[str, Any]]) -> dict[str, Any]:
    by_repeat = {str(m["repeat_idx"]): value for m, value in zip(repeats, values)}
    unique = []
    for value in values:
        if value not in unique:
            unique.append(value)
    consistent = len(unique) <= 1
    out: dict[str, Any] = {
        "consistent": consistent,
        "value": unique[0] if consistent and unique else None,
        "values_by_repeat": by_repeat,
    }
    if not consistent:
        out["distinct_values"] = unique
        out["anomaly"] = True
    return out


def _cross_table(steps: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for spec in CROSS_ROWS:
        matched = [s for s in steps if _matches(s, spec["match"])]
        if spec["id"] == "v8-timeout-kill":
            for step in matched:
                rows.append(_cross_row(spec, step))
            if not matched:
                rows.append(_cross_row(spec, None))
        elif not matched:
            rows.append(_cross_row(spec, None))
        else:
            rows.append(_cross_row(spec, matched[0]))
    filled = all(r["cell_filled"] for r in rows)
    return {
        "_comment": "缺一格不算完成。observed_rc 来自 repeats 共识；anomaly 则本格不能当最终答案。",
        "complete": filled,
        "rows": rows,
    }


def _cross_row(spec: dict[str, Any], step: dict[str, Any] | None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": spec["id"],
        "scene": spec["scene"],
        "has_real_error": spec["has_real_error"],
        "expected_rc": spec["expected_rc"],
        "cell_filled": step is not None,
        "observed_rc": None,
        "observed_signal": None,
        "observed_timed_out": None,
        "anomaly": False,
    }
    if spec.get("note"):
        row["_comment"] = spec["note"]
    if step is None:
        row["_comment"] = (row.get("_comment") or "") + " 本格缺失，交叉表未填完。"
        return row
    row["project"] = step["project"]
    row["cmd"] = step["cmd"]
    row["cache_state"] = step["cache_state"]
    row["observed_rc"] = step["rc"]["value"]
    row["observed_signal"] = step["signal"]["value"]
    row["observed_timed_out"] = step["timed_out"]["value"]
    row["anomaly"] = step["anomaly"]
    if step["rc"]["consistent"] and step["rc"]["value"] is not None:
        expected = spec["expected_rc"]
        rc = step["rc"]["value"]
        if expected == "0":
            row["matches_expected"] = rc == 0
        elif expected == "≠0":
            row["matches_expected"] = rc != 0
        elif expected == "124/137":
            row["matches_expected"] = rc in (124, 137) or step["timed_out"]["value"] is True
    return row


def _b9(steps: list[dict[str, Any]]) -> dict[str, Any]:
    matched = [
        s
        for s in steps
        if s["project"] == "np-syntax" and s["cmd"] == "V5" and s["cache_state"] == "WARM"
    ]
    if not matched:
        return {
            "_comment": "B9：有坏脚本的项目上 V5 是否仍启动成功且 rc=0。本 run 没有该 step。",
            "present": False,
        }
    step = matched[0]
    rc = step["rc"]["value"]
    timed_out = step["timed_out"]["value"]
    started_ok = (
        step["rc"]["consistent"]
        and step["timed_out"]["consistent"]
        and rc == 0
        and timed_out is False
    )
    return {
        "_comment": (
            "B9 观测：有坏脚本时 V5 仍 rc=0 且未 timeout → 启动成功不能证明脚本全部正确。"
            "本字段是观测，不是 CONFIRMED。"
        ),
        "present": True,
        "anomaly": step["anomaly"],
        "rc": rc,
        "timed_out": timed_out,
        "started_successfully_with_bad_scripts": started_ok,
    }


def _v8_liveness(steps: list[dict[str, Any]]) -> dict[str, Any]:
    matched = [s for s in steps if s["cmd"] == "V8"]
    observations: list[dict[str, Any]] = []
    for step in matched:
        rc = step["rc"]["value"]
        signal = step["signal"]["value"]
        timed_out = step["timed_out"]["value"]
        walls = [w for w in step["wall_time_by_repeat"].values() if isinstance(w, (int, float))]
        timeout = step.get("timeout_seconds")
        hang = False
        if timed_out is True:
            hang = True
        elif timeout is not None and walls and max(walls) >= float(timeout):
            hang = True
        crash_rc = rc in (134, 139, -11)
        crash_sig = signal == 11
        crash_text = bool(step.get("crash_mark_in_stderr_repeats"))
        leftover = False
        for extra in step.get("leftover_godot") or []:
            if extra.get("leftover_godot"):
                leftover = True
        debug_unusable = hang or crash_rc or crash_sig or crash_text
        observations.append(
            {
                "project": step["project"],
                "anomaly": step["anomaly"],
                "rc": rc,
                "signal": signal,
                "timed_out": timed_out,
                "wall_time_by_repeat": step["wall_time_by_repeat"],
                "hang": hang,
                "crash_rc_134_139": crash_rc,
                "signal_11": crash_sig,
                "crash_text": crash_text,
                "leftover_godot": leftover,
                "debug_unusable_observed": debug_unusable,
            }
        )
    return {
        "_comment": (
            "V8 存活性观测：wall≥timeout，或 rc∈{134,139}，或 stderr 含 "
            f"{CRASH_MARK!r}。任一成立只记观测，是否永久禁入 --debug 由人写报告。"
        ),
        "present": bool(observations),
        "runs": observations,
    }


def _matches(step: dict[str, Any], match: dict[str, str]) -> bool:
    mapping = {
        "group_id": "project",
        "cmd": "cmd",
        "cache_state": "cache_state",
    }
    for key, value in match.items():
        field = mapping.get(key, key)
        if step.get(field) != value:
            return False
    return True


def _iter_measurements(experiment_dir: Path) -> Iterable[dict[str, Any]]:
    for meta_path in sorted(experiment_dir.rglob("metadata.json")):
        repeat_dir = meta_path.parent
        cache_state = repeat_dir.parent.name
        if cache_state not in CACHE_STATES:
            continue
        status_path = repeat_dir / "process-status.json"
        if not status_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(meta, dict) or not isinstance(status, dict):
            continue
        try:
            repeat_idx = int(meta.get("repeat_idx", repeat_dir.name))
        except (TypeError, ValueError):
            continue
        leftover = None
        leftover_path = repeat_dir / "leftover-procs.json"
        if leftover_path.is_file():
            try:
                leftover = json.loads(leftover_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                leftover = None
        stderr = ""
        stderr_path = repeat_dir / "stderr.log"
        if stderr_path.is_file():
            stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
        yield {
            "N": meta.get("N") or experiment_dir.name,
            "run_id": meta.get("run_id") or experiment_dir.parent.name,
            "group_id": meta.get("group_id") or repeat_dir.parent.parent.parent.name,
            "step_id": meta.get("step_id") or repeat_dir.parent.parent.name,
            "cache_state": meta.get("cache_state") or cache_state,
            "repeat_idx": repeat_idx,
            "cmd": meta.get("cmd") or _cmd_from_step(repeat_dir.parent.parent.name),
            "target": meta.get("target"),
            "fixture": meta.get("fixture"),
            "inputs_digest": meta.get("inputs_digest"),
            "timeout_seconds": meta.get("timeout_seconds"),
            "status": {
                "rc": status.get("rc"),
                "signal": status.get("signal"),
                "timed_out": status.get("timed_out"),
                "wall_time": status.get("wall_time"),
            },
            "leftover": leftover,
            "crash_mark": CRASH_MARK in stderr,
        }


def _discover_experiment_dirs(path: Path) -> list[Path]:
    if _looks_like_experiment_dir(path):
        return [path]
    found: list[Path] = []
    for child in sorted(path.iterdir() if path.is_dir() else []):
        if child.is_dir() and _looks_like_experiment_dir(child):
            found.append(child)
    return found


def _looks_like_experiment_dir(path: Path) -> bool:
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
        return PROBE_ROOT / "reports" / rel / "exitcode"
    except ValueError:
        return experiment_dir / "exitcode"


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
