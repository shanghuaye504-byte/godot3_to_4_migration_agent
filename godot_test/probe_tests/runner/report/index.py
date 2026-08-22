"""生成 artifacts/<run-id>/index.md 证据索引。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_CACHE_STATES = {"COLD", "WARM", "PRESERVE"}
_MEASUREMENT_FILES = (
    "metadata.json",
    "argv.json",
    "stdout.log",
    "stderr.log",
    "process-status.json",
    "fs-before.json",
    "fs-after.json",
    "workspace.diff",
    "cache-manifest.json",
)


def _rel(path: Path, run_dir: Path) -> str:
    return path.relative_to(run_dir).as_posix()


def _file_mark(path: Path) -> str:
    return "`" + path.name + "`" if path.is_file() else "—"


def _iter_measurements(exp_dir: Path):
    for group_dir in sorted(p for p in exp_dir.iterdir() if p.is_dir()):
        for step_dir in sorted(p for p in group_dir.iterdir() if p.is_dir()):
            for cache_dir in sorted(p for p in step_dir.iterdir() if p.is_dir() and p.name in _CACHE_STATES):
                for repeat_dir in sorted(
                    p for p in cache_dir.iterdir() if p.is_dir() and p.name.isdigit()
                ):
                    yield group_dir, step_dir.name, cache_dir.name, repeat_dir.name, repeat_dir


def write_run_index(
    run_dir: Path,
    *,
    run_id: Optional[str] = None,
    summary: Optional[dict] = None,
) -> Path:
    """扫描一次 run 的 artifacts，写出 index.md。返回写入路径。"""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_id or run_dir.name
    fake = bool((summary or {}).get("fake", False))

    lines = [
        f"# {run_id}",
        "",
        "证据索引。路径含 group / cache_state / repeat，避免互相覆盖。",
    ]
    if fake:
        lines.append("")
        lines.append("> 本 run 使用 Fake Godot，**不得**作为已确认结论引用。")
    lines.extend(["", f"Run ID: `{run_id}`", ""])

    if summary:
        lines.append("## 摘要")
        lines.append("")
        lines.append("```json")
        lines.append(
            json.dumps(
                {
                    "exp_id": summary.get("exp_id"),
                    "fake": summary.get("fake"),
                    "groups": summary.get("groups"),
                    "analyze_hint": (
                        f"python Analyzer.py --path {summary.get('artifact_dir')}"
                        if summary.get("artifact_dir")
                        else None
                    ),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        lines.append("```")
        lines.append("")

    exp_dirs = sorted(p for p in run_dir.iterdir() if p.is_dir())
    if not exp_dirs:
        lines.extend(["（尚无实验产物）", ""])
    for exp_dir in exp_dirs:
        lines.append(f"## {exp_dir.name}")
        lines.append("")
        for name in ("groups.json",):
            path = exp_dir / name
            if path.is_file():
                lines.append(f"- 实验级 `{name}`: `{_rel(path, run_dir)}`")
        lines.append("")
        lines.append("| Group | Step | Cache | Repeat | stdout | stderr | metadata | 目录 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for group_dir, step_id, cache_state, repeat_idx, repeat_dir in _iter_measurements(exp_dir):
            lines.append(
                "| {group} | {step} | {cache} | {repeat} | {stdout} | {stderr} | {meta} | `{rel}` |".format(
                    group=group_dir.name,
                    step=step_id,
                    cache=cache_state,
                    repeat=repeat_idx,
                    stdout=_file_mark(repeat_dir / "stdout.log"),
                    stderr=_file_mark(repeat_dir / "stderr.log"),
                    meta=_file_mark(repeat_dir / "metadata.json"),
                    rel=_rel(repeat_dir, run_dir),
                )
            )
            missing = [name for name in _MEASUREMENT_FILES if not (repeat_dir / name).is_file()]
            if missing:
                lines.append(f"| | | | | 缺文件: {', '.join(missing)} | | | |")
        lines.append("")
        cleanup_rows = sorted(exp_dir.glob("*/cleanup.json"))
        if cleanup_rows:
            lines.append("### Cleanup")
            lines.append("")
            for cleanup_path in cleanup_rows:
                lines.append(f"- `{_rel(cleanup_path, run_dir)}`")
            lines.append("")

    index_path = run_dir / "index.md"
    index_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return index_path
