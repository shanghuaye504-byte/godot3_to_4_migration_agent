"""L5：冻结基线，并区分新错误与旧账。

在转换器之后、模型改文件之前，把当时的错误指纹写入 scene_baseline。
同时把当时每个脚本的 class_name 和 func 写入 scene_member_baseline。
这两张表冻结后只读，重新索引不得改写它们。
现在有、快照没有的错误是 regression；两边都有的是旧账；快照有、现在没有的是 fixed。
E_MEMBER_GONE 只比较 class 与 func。引擎自带名字不在快照里，不报。
目标脚本语法失败时弃权。

契约见 codebase_index/NEXT_STEP.md 第 6 节。
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field

from codeindex.scene.rules import Problem

__all__ = ["freeze_baseline", "diff_baseline", "member_gone_problems"]


def _fingerprint(code: str, path: str, subject: str) -> str:
    return hashlib.sha1(f"{code}|{path}|{subject}".encode()).hexdigest()


# ---------------------------------------------------------------------------
# 冻结
# ---------------------------------------------------------------------------


def freeze_baseline(conn: sqlite3.Connection, problems: list[Problem]) -> None:
    """把当前全部 problem 的 fingerprint 写入 scene_baseline，同时冻结成员快照。

    冻结后这两张表只读，不随后续重新索引更新。
    """
    conn.execute("DELETE FROM scene_baseline")
    conn.execute("DELETE FROM scene_member_baseline")
    for p in problems:
        conn.execute(
            "INSERT OR IGNORE INTO scene_baseline (fingerprint, path, code, tier, subject) "
            "VALUES (?,?,?,?,?)",
            (p.fingerprint, p.path, p.code, p.tier, p.subject),
        )
    # 冻结成员快照：当前 symbols 表里的 class_name 和 func
    for row in conn.execute(
        "SELECT f.path, s.kind, s.name "
        "FROM symbols s JOIN files f ON f.id = s.file_id "
        "WHERE s.kind IN ('class', 'func')"
    ):
        conn.execute(
            "INSERT OR IGNORE INTO scene_member_baseline (script_path, kind, name) "
            "VALUES (?,?,?)",
            (row[0], row[1], row[2]),
        )


# ---------------------------------------------------------------------------
# 三分法
# ---------------------------------------------------------------------------


@dataclass
class DiffResult:
    regression: list[Problem] = field(default_factory=list)
    pre_existing_count: int = 0
    pre_existing_by_code: dict[str, int] = field(default_factory=dict)
    fixed: list[dict] = field(default_factory=list)


def diff_baseline(conn: sqlite3.Connection, current: list[Problem]) -> DiffResult:
    """把当前 problem 集合与 baseline 对比，分 regression / pre_existing / fixed。"""
    result = DiffResult()
    baseline_fps: dict[str, tuple[str, str]] = {}
    for row in conn.execute("SELECT fingerprint, code, path FROM scene_baseline"):
        baseline_fps[row[0]] = (row[1], row[2])

    current_fps: set[str] = set()
    for p in current:
        current_fps.add(p.fingerprint)
        if p.fingerprint in baseline_fps:
            result.pre_existing_count += 1
            result.pre_existing_by_code[p.code] = result.pre_existing_by_code.get(p.code, 0) + 1
        else:
            result.regression.append(p)

    for fp, (code, path) in baseline_fps.items():
        if fp not in current_fps:
            result.fixed.append({"fingerprint": fp, "code": code, "path": path})

    return result


# ---------------------------------------------------------------------------
# E_MEMBER_GONE
# ---------------------------------------------------------------------------


def member_gone_problems(conn: sqlite3.Connection) -> tuple[list[Problem], list[dict]]:
    """对比 member_baseline 与当前符号表，报 E_MEMBER_GONE。

    返回 (problems, suppressed_checks)。
    引擎自带名字不在快照里，不会误报。脚本语法失败时弃权。
    """
    problems: list[Problem] = []
    suppressed: list[dict] = []

    # 快照
    baseline_members: dict[str, list[tuple[str, str]]] = {}
    for row in conn.execute("SELECT script_path, kind, name FROM scene_member_baseline"):
        baseline_members.setdefault(row[0], []).append((row[1], row[2]))

    if not baseline_members:
        return problems, suppressed

    for script_path, members in baseline_members.items():
        # 该脚本当前是否语法失败（symbols 被清空）
        file_row = conn.execute(
            "SELECT id FROM files WHERE path = ?", (script_path,)
        ).fetchone()
        if file_row is None:
            # 文件已删除：所有成员都消失，但不报 E_MEMBER_GONE（文件都没了，不是改名）
            continue
        file_id = file_row[0]
        current_symbols = {
            (row[0], row[1])
            for row in conn.execute(
                "SELECT kind, name FROM symbols WHERE file_id = ?", (file_id,)
            )
        }
        if not current_symbols:
            # 语法失败（户口还在、符号为空）→ 弃权
            suppressed.append({
                "path": script_path,
                "node_path": None,
                "reason": f"脚本 {script_path} 语法失败，E_MEMBER_GONE 弃权",
            })
            continue

        for kind, name in members:
            if (kind, name) in current_symbols:
                continue  # 还在
            # 消失了。检查场景是否仍引用。
            if kind == "class":
                ref = conn.execute(
                    "SELECT path, line, col, node_path FROM scene_refs "
                    "WHERE kind = 'node_type' AND symbol = ? LIMIT 1",
                    (name,),
                ).fetchone()
            else:  # func
                ref = conn.execute(
                    "SELECT path, line, col, node_path FROM scene_refs "
                    "WHERE kind = 'conn_method' AND symbol = ? LIMIT 1",
                    (name,),
                ).fetchone()
            if ref is None:
                continue  # 场景没引用，不报
            ref_path, ref_line, ref_col, ref_node_path = ref
            subject = f"{kind}:{name}@{script_path}"
            problems.append(
                Problem(
                    fingerprint=_fingerprint("E_MEMBER_GONE", ref_path, subject),
                    code="E_MEMBER_GONE",
                    tier="ERROR",
                    path=ref_path,
                    line=ref_line or 1,
                    col=ref_col or 1,
                    node_path=ref_node_path,
                    subject=subject,
                    message=f"{'类' if kind == 'class' else '函数'} {name} 已从 {script_path} 删除，场景仍引用",
                    evidence="",
                )
            )

    return problems, suppressed
