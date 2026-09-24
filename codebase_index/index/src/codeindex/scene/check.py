"""L5：组装 codeindex scene-check 的返回。

调用 rules 与 baseline，输出 regression / pre_existing / fixed / coverage。
不传路径时全量；传入路径时用 scene_refs.target_file 反查相关场景。
不写盘，不拦 edit。有 regression 时仍由 CLI 返回退出码 0。

契约见 codebase_index/NEXT_STEP.md 第 6.4 节。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from codeindex.scene.baseline import diff_baseline, member_gone_problems
from codeindex.scene.rules import Problem, check_scene

__all__ = ["scene_check"]


def _problem_to_dict(p: Problem) -> dict[str, Any]:
    return {
        "fingerprint": p.fingerprint,
        "code": p.code,
        "tier": p.tier,
        "path": p.path,
        "line": p.line,
        "col": p.col,
        "node_path": p.node_path,
        "subject": p.subject,
        "message": p.message,
        "evidence": p.evidence,
    }


def scene_check(
    conn: sqlite3.Connection,
    project_root: Path,
    *,
    paths: list[str] | None = None,
    rules_db_path: Path | None = None,
) -> dict[str, Any]:
    """全量或按路径闭包跑 L4+L5，返回 scene-check 的 JSON 结构。"""
    # 确定要检查的场景文件集合
    if paths:
        scene_files = _path_closure(conn, paths)
    else:
        scene_files = [
            row[0] for row in conn.execute(
                "SELECT path FROM scene_files WHERE parse_status = 'OK' OR parse_status = 'MALFORMED'"
            )
        ]

    # 本仓库所有 class_name
    repo_classes = {
        row[0] for row in conn.execute(
            "SELECT DISTINCT name FROM symbols WHERE kind = 'class'"
        )
    }

    # 对每个场景文件现算 L4
    all_problems: list[Problem] = []
    all_suppressed: list[dict] = []
    rules_unavailable = False

    for scene_path in scene_files:
        abs_path = project_root / scene_path
        if not abs_path.exists():
            continue
        text = abs_path.read_bytes().decode("utf-8", errors="replace")
        result = check_scene(
            text, scene_path,
            repo_classes=repo_classes,
            rules_db_path=rules_db_path,
            file_exists=lambda rf: (project_root / rf).exists(),
        )
        all_problems.extend(result.problems)
        all_suppressed.extend(result.suppressed_checks)
        if result.rules_unavailable:
            rules_unavailable = True

    # L5：E_MEMBER_GONE
    member_problems, member_suppressed = member_gone_problems(conn)
    all_problems.extend(member_problems)
    all_suppressed.extend(member_suppressed)

    # 三分法
    diff = diff_baseline(conn, all_problems)

    # coverage
    total = conn.execute("SELECT COUNT(*) FROM scene_files").fetchone()[0]
    ok = conn.execute("SELECT COUNT(*) FROM scene_files WHERE parse_status = 'OK'").fetchone()[0]
    parse_failed = [
        row[0] for row in conn.execute(
            "SELECT path FROM scene_files WHERE parse_status = 'MALFORMED'"
        )
    ]
    oversize = [
        row[0] for row in conn.execute(
            "SELECT path FROM scene_files WHERE parse_status = 'SKIPPED_OVERSIZE'"
        )
    ]
    binary = [
        row[0] for row in conn.execute(
            "SELECT path FROM scene_files WHERE parse_status = 'BINARY'"
        )
    ]
    stale_count = conn.execute(
        "SELECT COUNT(*) FROM scene_files WHERE mtime > indexed_at"
    ).fetchone()[0]

    by_code: dict[str, int] = {}
    for p in all_problems:
        by_code[p.code] = by_code.get(p.code, 0) + 1

    return {
        "regression": [_problem_to_dict(p) for p in diff.regression],
        "pre_existing": {
            "count": diff.pre_existing_count,
            "by_code": diff.pre_existing_by_code,
        },
        "fixed": diff.fixed,
        "coverage": {
            "files_total": total,
            "files_ok": ok,
            "files_parse_failed": parse_failed,
            "files_skipped_oversize": oversize,
            "files_binary": binary,
            "suppressed_checks": all_suppressed,
            "rules_unavailable": rules_unavailable,
            "scene_index_stale": stale_count > 0,
        },
        "summary": {
            "error": len(all_problems),
            "by_code": by_code,
        },
    }


def _path_closure(conn: sqlite3.Connection, paths: list[str]) -> list[str]:
    """传入 .gd 时，用 scene_refs.target_file 反查引用它的场景。"""
    scenes: set[str] = set()
    for p in paths:
        # 如果本身是场景文件，直接加
        if p.endswith((".tscn", ".tres")):
            scenes.add(p)
            continue
        # 反查引用了这个 .gd 的场景
        for row in conn.execute(
            "SELECT DISTINCT path FROM scene_refs WHERE target_file = ?", (p,)
        ):
            scenes.add(row[0])
    return sorted(scenes)
