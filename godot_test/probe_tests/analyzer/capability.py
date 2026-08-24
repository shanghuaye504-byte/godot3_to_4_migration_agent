#!/usr/bin/env python3
"""analyzer/capability.py —— 只提取能力与职责矩阵，无对错。

用法：
    python analyzer/capability.py artifacts/<run-id>/N15/
    python analyzer/capability.py artifacts/<run-id>/N15/ --out reports/<run-id>/N15/capability/

服务：N15
输入：已落盘的 N15 目录（--help 原文、各独立副本的 diff / stdout / process-status）
输出：reports/<run-id>/N15/capability/capability.json

提取：
    convert / 3to4 / upgrade 相关 CLI 入口是否存在（以 --help 原文为准，不以源码存在为准）
    --validate-conversion-3to4 / --convert-3to4 能否对最小 config_version=4 项目调用
    --convert-3to4 是否真的改了文件（以 diff 为准，不看 stdout）
    --convert-3to4 是否接受 max_file_kb / max_line_size 参数
    upgrade tool 改了哪些文件类型（GDScript、UID、.tscn、.tres、资源路径、import cache）
    用 V3 --import 近似替代 upgrade tool 时的边界

本脚本只出能力矩阵，不宣布流水线形状、不写 CONFIRMED。
「报告成功但文件未变化」本身就是一条要记录的观测。

禁止：import 实验脚本；修改 artifacts/；写死 fixture 名。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROBE_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    artifact_root = _resolve_existing(args.artifact_dir)
    experiment_dirs = _discover_experiment_dirs(artifact_root)
    if not experiment_dirs:
        sys.stderr.write(f"no N15 experiment directory under {artifact_root}\n")
        return 2

    written: list[Path] = []
    for exp_dir in experiment_dirs:
        report = analyze_experiment(exp_dir)
        out_dir = _default_out_dir(exp_dir) if args.out is None else Path(args.out)
        if args.out is not None and len(experiment_dirs) > 1:
            out_dir = Path(args.out) / report["N"] / "capability"
        out_dir = out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / "capability.json"
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
        description="Capability analyzer: converter / upgrade-tool CLI capability matrix (no verdicts)."
    )
    parser.add_argument("artifact_dir", help="artifacts/<run-id>/N15 (or artifacts/<run-id>)")
    parser.add_argument(
        "--out",
        default=None,
        help="output directory (default: reports/<run-id>/N15/capability/)",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------


def analyze_experiment(exp_dir: Path) -> dict[str, Any]:
    run_meta = _read_json(exp_dir / "run.json") or {}
    help_entries = _analyze_help(exp_dir / "help" / "1")
    validate = _analyze_simple_step(
        exp_dir / "validate" / "validate-conversion-3to4" / "COLD" / "1",
        extra_files=("content-unchanged.json",),
    )
    convert = _analyze_convert_step(exp_dir / "convert" / "convert-3to4" / "COLD" / "1")
    convert_args = _analyze_convert_step(
        exp_dir / "convert-args" / "convert-3to4-args" / "COLD" / "1",
        extra_files=("args-echo.json",),
    )
    upgrade_tool = _read_json(exp_dir / "upgrade-tool" / "skip.json") or {
        "found": None,
        "reason": "upgrade-tool/skip.json missing",
    }
    v3_raw = _analyze_v3_boundary_raw(exp_dir / "v3-boundary-raw" / "v3" / "COLD" / "1")
    v3_converted = _analyze_v3_boundary_converted(exp_dir / "v3-boundary-converted")

    responsibility_matrix = _build_responsibility_matrix(
        convert=convert,
        v3_raw=v3_raw,
        v3_converted=v3_converted,
    )

    return {
        "_comment": (
            "converter / upgrade-tool CLI 能力矩阵，只做事实提取，不宣布流水线形状、"
            "不写 CONFIRMED。「报告成功但文件未变化」等异常本身作为一条观测保留。"
        ),
        "analyzer": "capability",
        "run_id": run_meta.get("run_id") or exp_dir.parent.name,
        "N": run_meta.get("N") or exp_dir.name,
        "artifact_dir": str(exp_dir),
        "inputs_digest": run_meta.get("inputs_digest"),
        "godot": run_meta.get("godot"),
        "cli_entry_points": help_entries,
        "validate_conversion_3to4": validate,
        "convert_3to4": convert,
        "convert_3to4_with_size_args": convert_args,
        "convert_3to4_args_consistent_with_no_args": _compare_changed_paths(
            convert, convert_args
        ),
        "upgrade_tool_entry": upgrade_tool,
        "v3_alone_on_unconverted_project": v3_raw,
        "v3_after_convert_3to4": v3_converted,
        "responsibility_matrix": responsibility_matrix,
    }


def _analyze_help(help_dir: Path) -> dict[str, Any]:
    status = _read_json(help_dir / "process-status.json") or {}
    flags = _read_json(help_dir / "flags-found.json") or {}
    entries = {}
    for keyword, hits in flags.items():
        entries[keyword] = {"found": bool(hits), "hits": hits}
    return {
        "help_callable": status.get("rc") == 0 and not status.get("timed_out"),
        "rc": status.get("rc"),
        "timed_out": status.get("timed_out"),
        "entries": entries,
    }


def _analyze_simple_step(step_dir: Path, *, extra_files: tuple[str, ...] = ()) -> dict[str, Any]:
    status = _read_json(step_dir / "process-status.json") or {}
    record: dict[str, Any] = {
        "callable": status.get("rc") == 0 and not status.get("timed_out"),
        "rc": status.get("rc"),
        "timed_out": status.get("timed_out"),
        "wall_time": status.get("wall_time"),
    }
    for name in extra_files:
        data = _read_json(step_dir / name)
        if data is not None:
            record[name.replace(".json", "").replace("-", "_")] = data
    return record


def _analyze_convert_step(step_dir: Path, *, extra_files: tuple[str, ...] = ()) -> dict[str, Any]:
    record = _analyze_simple_step(step_dir, extra_files=extra_files)
    summary = _read_json(step_dir / "file-change-summary.json") or []
    project_changes = [
        row for row in summary if not str(row.get("path", "")).startswith(".godot/")
    ]
    mismatches = [row for row in project_changes if row.get("mismatch")]
    record["changes_files"] = any(row.get("actually_changed") for row in project_changes)
    record["changed_paths"] = sorted(
        row["path"] for row in project_changes if row.get("actually_changed")
    )
    record["reported_success_but_unchanged"] = sorted(
        row["path"]
        for row in project_changes
        if row.get("reported_changed") is True and not row.get("actually_changed")
    )
    record["mismatch_count"] = len(mismatches)
    record["file_change_summary"] = summary
    return record


def _compare_changed_paths(convert: dict[str, Any], convert_args: dict[str, Any]) -> dict[str, Any]:
    a = set(convert.get("changed_paths") or [])
    b = set(convert_args.get("changed_paths") or [])
    return {
        "accepts_size_args": convert_args.get("callable"),
        "same_changed_paths_as_no_args": a == b,
        "only_in_no_args": sorted(a - b),
        "only_in_with_args": sorted(b - a),
    }


def _analyze_v3_boundary_raw(step_dir: Path) -> dict[str, Any]:
    status = _read_json(step_dir / "process-status.json") or {}
    stderr = _read_text(step_dir / "stderr.log")
    error_lines = [
        line for line in stderr.splitlines() if "ERROR" in line and line.strip()
    ]
    return {
        "_comment": (
            "V3 单独作用于未转换（3.x 语法 / config_version=4）项目的观测："
            "rc 是否为 0 与 stderr 是否含 ERROR/SCRIPT ERROR 分开记录——"
            "rc 不可信已由 N08 确认，这里只再次留证。"
        ),
        "rc": status.get("rc"),
        "timed_out": status.get("timed_out"),
        "error_lines": error_lines,
        "errors_present": bool(error_lines),
    }


def _analyze_v3_boundary_converted(group_dir: Path) -> dict[str, Any]:
    convert_step = _analyze_convert_step(group_dir / "convert-3to4" / "COLD" / "1")
    v3_status = _read_json(group_dir / "v3" / "COLD" / "1" / "process-status.json") or {}
    v3_diff = _read_text(group_dir / "v3" / "COLD" / "1" / "workspace.diff")
    added_paths = [
        line[2:].split("  ", 1)[0].strip()
        for line in v3_diff.splitlines()
        if line.startswith("+ ")
    ]
    uid_sidecars = [p for p in added_paths if p.endswith(".uid")]
    godot_cache_paths = [p for p in added_paths if p.startswith(".godot/")]
    non_cache_new = [p for p in added_paths if not p.startswith(".godot/") and not p.endswith(".uid")]
    return {
        "_comment": (
            "先跑 convert-3to4 再跑 V3：观测 V3 在文本已转换后还会新增哪些文件"
            "（UID sidecar / import 缓存），以及是否还有除此之外的文本级改写。"
        ),
        "convert_step": convert_step,
        "v3_rc": v3_status.get("rc"),
        "v3_timed_out": v3_status.get("timed_out"),
        "v3_added_paths": added_paths,
        "v3_uid_sidecars_generated": uid_sidecars,
        "v3_godot_cache_paths_generated": godot_cache_paths,
        "v3_added_non_cache_non_uid_paths": non_cache_new,
    }


def _build_responsibility_matrix(
    *,
    convert: dict[str, Any],
    v3_raw: dict[str, Any],
    v3_converted: dict[str, Any],
) -> dict[str, Any]:
    def _by_ext(paths: list[str]) -> dict[str, list[str]]:
        by_ext: dict[str, list[str]] = {}
        for path in paths:
            ext = Path(path).suffix or "(no-ext)"
            by_ext.setdefault(ext, []).append(path)
        return {ext: sorted(items) for ext, items in sorted(by_ext.items())}

    return {
        "_comment": (
            "工具 × 文件类型 × 动作，纯事实汇总，不判断正确性。"
            "convert-3to4 改文本；V3(after convert) 只补 UID/缓存；"
            "V3(on unconverted) 不做任何文本改写，只报错。"
        ),
        "convert_3to4": {
            "action": "text-rewrite-and-rename",
            "touched_by_extension": _by_ext(convert.get("changed_paths") or []),
        },
        "v3_import_after_convert": {
            "action": "uid-sidecar-and-import-cache-only",
            "uid_sidecars_by_extension": _by_ext(
                v3_converted.get("v3_uid_sidecars_generated") or []
            ),
            "other_new_files": v3_converted.get("v3_added_non_cache_non_uid_paths") or [],
        },
        "v3_import_on_unconverted": {
            "action": "none-fails-with-parse-or-load-errors",
            "errors_present": v3_raw.get("errors_present"),
        },
    }


# ---------------------------------------------------------------------------
# io helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _discover_experiment_dirs(path: Path) -> list[Path]:
    if _looks_like_n15_dir(path):
        return [path]
    found: list[Path] = []
    for child in sorted(path.iterdir() if path.is_dir() else []):
        if child.is_dir() and _looks_like_n15_dir(child):
            found.append(child)
    return found


def _looks_like_n15_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    run_meta = _read_json(path / "run.json")
    if isinstance(run_meta, dict) and run_meta.get("N") == "N15":
        return True
    return path.name == "N15" and (path / "index.md").is_file()


def _default_out_dir(experiment_dir: Path) -> Path:
    experiment_dir = experiment_dir.resolve()
    artifacts_dir = PROBE_ROOT / "artifacts"
    try:
        rel = experiment_dir.relative_to(artifacts_dir)
        return PROBE_ROOT / "reports" / rel / "capability"
    except ValueError:
        return experiment_dir / "capability"


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


if __name__ == "__main__":
    sys.exit(main())
