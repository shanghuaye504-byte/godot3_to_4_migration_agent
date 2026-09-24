"""L4：场景 ERROR。每次现算，不把问题缓存进数据库。

把语法级 P_ 问题提升为 E_PARSE_*。
判断根数量、资源编号、父路径、未转换的 format、旧类名黑名单、嵌套成环。
文件没读完，或问题落在看不全的子树上时弃权，写入 suppressed_checks。
弃权看节点路径，不看 subject 字符串。
migration_rules_db 缺失时跳过 E_UNMIGRATED_TYPE，并标明 rules_unavailable。
不 import rag。

契约见 codebase_index/NEXT_STEP.md 第 5 节。
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

from codeindex.scene.model import parse_scene
from codeindex.scene.resolve import SceneModel, resolve

__all__ = ["Problem", "CheckResult", "check_scene"]


@dataclass
class Problem:
    """L4 的可证 ERROR。fingerprint 不含行号。"""

    fingerprint: str
    code: str
    tier: Literal["ERROR"]
    path: str
    line: int  # 1-based
    col: int
    node_path: str | None
    subject: str  # 稳定标识，不含行号
    message: str
    evidence: str  # 原文切片，来自 span


@dataclass
class CheckResult:
    problems: list[Problem] = field(default_factory=list)
    suppressed_checks: list[dict] = field(default_factory=list)
    rules_unavailable: bool = False


def _fingerprint(code: str, path: str, subject: str) -> str:
    return hashlib.sha1(f"{code}|{path}|{subject}".encode()).hexdigest()


def _in_unresolved(node_path: str | None, unresolved: list[str]) -> bool:
    if node_path is None:
        return False
    for prefix in unresolved:
        if prefix == ".":
            return True
        if node_path == prefix or node_path.startswith(prefix + "/"):
            return True
    return False


def _suppress(result: CheckResult, path: str, node_path: str | None, reason: str) -> None:
    result.suppressed_checks.append({"path": path, "node_path": node_path, "reason": reason})


def _emit(
    result: CheckResult,
    code: str,
    path: str,
    line: int,
    col: int,
    node_path: str | None,
    subject: str,
    message: str,
    evidence: str,
    model: SceneModel,
) -> None:
    """报一条 ERROR，或按弃权规则记入 suppressed_checks。"""
    if model.is_inherited or _in_unresolved(node_path, model.unresolved_subtrees):
        _suppress(result, path, node_path, f"{code} 落在实例子树/继承场景弃权范围")
        return
    result.problems.append(
        Problem(
            fingerprint=_fingerprint(code, path, subject),
            code=code,
            tier="ERROR",
            path=path,
            line=line,
            col=col,
            node_path=node_path,
            subject=subject,
            message=message,
            evidence=evidence,
        )
    )


def _load_migrated_types(rules_db_path: Path | None) -> tuple[set[str], bool]:
    """从 rules.db 读出 symbol_kind='class' 的 old_symbol 集合。"""
    if rules_db_path is None or not rules_db_path.is_file():
        return set(), True
    try:
        conn = sqlite3.connect(f"file:{rules_db_path}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT old_symbol FROM rules WHERE symbol_kind = 'class'"
            ).fetchall()
            return {r[0] for r in rows}, False
        finally:
            conn.close()
    except sqlite3.Error:
        return set(), True


def check_scene(
    text: str,
    path: str,
    *,
    repo_classes: set[str] | None = None,
    rules_db_path: Path | None = None,
    file_exists=None,
) -> CheckResult:
    """对一个 .tscn / .tres 现算全部 L4 ERROR。纯函数，不缓存。"""
    result = CheckResult()
    doc = parse_scene(text, path)
    model = resolve(doc)
    repo_classes = repo_classes or set()

    # parse_status != OK → 语法问题提升为 E_PARSE_*，后续语义检查弃权
    if doc.problems:
        for p in doc.problems:
            result.problems.append(
                Problem(
                    fingerprint=_fingerprint(f"E_PARSE_{p.code}", path, p.message),
                    code=f"E_PARSE_{p.code}",
                    tier="ERROR",
                    path=path,
                    line=p.span.line,
                    col=p.span.col,
                    node_path=None,
                    subject=p.message,
                    message=p.message,
                    evidence=text[p.span.byte_start : p.span.byte_end],
                )
            )
        _suppress(result, path, None, "parse_status != OK，跳过后续语义检查")
        return result

    migrated_types, rules_unavailable = _load_migrated_types(rules_db_path)
    result.rules_unavailable = rules_unavailable

    # E_NOT_CONVERTED
    if model.format == 2:
        result.problems.append(
            Problem(
                fingerprint=_fingerprint("E_NOT_CONVERTED", path, "format"),
                code="E_NOT_CONVERTED", tier="ERROR", path=path,
                line=1, col=1, node_path=None, subject="format",
                message="文件仍是 Godot 3 文本（format=2）", evidence="",
            )
        )

    # E_NO_SCENE_ROOT / E_MULTIPLE_ROOTS
    if doc.doc_kind == "scene":
        if len(model.root_paths) == 0:
            result.problems.append(
                Problem(
                    fingerprint=_fingerprint("E_NO_SCENE_ROOT", path, "root"),
                    code="E_NO_SCENE_ROOT", tier="ERROR", path=path,
                    line=1, col=1, node_path=None, subject="root",
                    message="场景没有根节点", evidence="",
                )
            )
        elif len(model.root_paths) > 1:
            result.problems.append(
                Problem(
                    fingerprint=_fingerprint("E_MULTIPLE_ROOTS", path, "root"),
                    code="E_MULTIPLE_ROOTS", tier="ERROR", path=path,
                    line=1, col=1, node_path=None, subject="root",
                    message=f"场景有 {len(model.root_paths)} 个根节点", evidence="",
                )
            )

    # E_EXT_ID_UNDECLARED / E_SUB_ID_UNDECLARED
    for ref in model.refs:
        if ref.kind == "ext_use" and ref.value not in model.ext:
            _emit(
                result, "E_EXT_ID_UNDECLARED", path, ref.span.line, ref.span.col,
                ref.node_path, f"ext:{ref.value}",
                f'ExtResource("{ref.value}") 无对应声明', "", model,
            )
        elif ref.kind == "sub_use" and ref.value not in model.sub:
            _emit(
                result, "E_SUB_ID_UNDECLARED", path, ref.span.line, ref.span.col,
                ref.node_path, f"sub:{ref.value}",
                f'SubResource("{ref.value}") 无对应声明', "", model,
            )

    # E_DUPLICATE_EXT_ID / E_DUPLICATE_SUB_ID
    for kind, sec_kind, code in (
        ("ext", "ext_resource", "E_DUPLICATE_EXT_ID"),
        ("sub", "sub_resource", "E_DUPLICATE_SUB_ID"),
    ):
        seen: set[str] = set()
        for sec in doc.sections:
            if sec.kind != sec_kind:
                continue
            rid = _sec_id(sec)
            if rid is None:
                continue
            if rid in seen:
                result.problems.append(
                    Problem(
                        fingerprint=_fingerprint(code, path, f"{kind}:{rid}"),
                        code=code, tier="ERROR", path=path,
                        line=sec.heading_span.line, col=sec.heading_span.col,
                        node_path=None, subject=f"{kind}:{rid}",
                        message=f'{sec_kind} id "{rid}" 声明了两次', evidence="",
                    )
                )
            seen.add(rid)

    # E_EXT_PATH_MISSING
    if file_exists is not None:
        for ext in model.ext.values():
            if ext.ref_path is None:
                continue
            resolved = _resolve_path(ext.ref_path, path)
            if resolved is None or not file_exists(resolved):
                result.problems.append(
                    Problem(
                        fingerprint=_fingerprint("E_EXT_PATH_MISSING", path, f"ext:{ext.id}"),
                        code="E_EXT_PATH_MISSING", tier="ERROR", path=path,
                        line=ext.span.line, col=ext.span.col,
                        node_path=None, subject=f"ext:{ext.id}",
                        message=f'外部资源路径 "{ext.ref_path}" 解析不到文件', evidence="",
                    )
                )

    # E_SCRIPT_REF_NOT_SCRIPT
    for ref in model.refs:
        if ref.kind == "script_ref":
            ext = model.ext.get(ref.value)
            if ext is not None and ext.ref_path is not None and not ext.ref_path.endswith(".gd"):
                _emit(
                    result, "E_SCRIPT_REF_NOT_SCRIPT", path,
                    ref.span.line, ref.span.col,
                    ref.node_path, f"script:{ref.value}",
                    f"script 指向的不是 .gd：{ext.ref_path}", "", model,
                )

    # E_NODE_PARENT_MISSING
    for node in model.nodes:
        if node.parent is not None and node.parent != "." and node.parent not in model.node_by_path:
            _emit(
                result, "E_NODE_PARENT_MISSING", path,
                node.heading_span.line, node.heading_span.col,
                node.node_path, f"parent:{node.parent}@{node.node_path}",
                f'父路径 "{node.parent}" 在本文件不存在', "", model,
            )

    # E_NODE_NO_TYPE
    for node in model.nodes:
        if node.type is None and not node.has_instance and not node.has_instance_placeholder:
            _emit(
                result, "E_NODE_NO_TYPE", path,
                node.heading_span.line, node.heading_span.col,
                node.node_path, f"type:{node.node_path}",
                f'节点 "{node.node_path}" 无 type / instance / instance_placeholder', "", model,
            )

    # E_CONN_NODE_MISSING
    for conn in model.conns:
        for label, cpath in (("from", conn.from_path), ("to", conn.to_path)):
            if cpath is not None and cpath != "." and cpath not in model.node_by_path:
                _emit(
                    result, "E_CONN_NODE_MISSING", path,
                    conn.span.line, conn.span.col,
                    cpath, f"conn:{label}:{cpath}",
                    f'连接 {label}="{cpath}" 在本文件不存在', "", model,
                )

    # E_UNMIGRATED_TYPE
    if not rules_unavailable:
        for ref in model.refs:
            if ref.kind in ("node_type", "res_type") and ref.value in migrated_types and ref.value not in repo_classes:
                _emit(
                    result, "E_UNMIGRATED_TYPE", path,
                    ref.span.line, ref.span.col,
                    ref.node_path, f"type:{ref.value}",
                    f'类型 "{ref.value}" 是 Godot 3 旧类名', "", model,
                )

    # E_INSTANCE_CYCLE（自引用）。这是图事实，不是「本地找不到」，不因 instance 子树弃权。
    for ref in model.refs:
        if ref.kind == "instance":
            ext = model.ext.get(ref.value)
            if ext is not None and ext.ref_path is not None:
                resolved = _resolve_path(ext.ref_path, path)
                if resolved is not None and resolved == path:
                    result.problems.append(
                        Problem(
                            fingerprint=_fingerprint("E_INSTANCE_CYCLE", path, f"instance:{ref.node_path}"),
                            code="E_INSTANCE_CYCLE", tier="ERROR", path=path,
                            line=ref.span.line, col=ref.span.col,
                            node_path=ref.node_path, subject=f"instance:{ref.node_path}",
                            message=f'节点 "{ref.node_path}" instance 指向本文件，构成环',
                            evidence="",
                        )
                    )

    return result


def _sec_id(sec) -> str | None:
    v = sec.attrs.get("id")
    if v is None:
        return None
    if v.kind == "int":
        return v.raw
    if v.kind == "str":
        return v.raw.strip('"')
    return None


def _resolve_path(ref_path: str, current_path: str) -> str | None:
    p = ref_path.split("::")[0]
    if not p:
        return None
    if p.startswith("res://"):
        return p[6:]
    if p.startswith("uid://"):
        return None
    base = PurePosixPath(current_path).parent
    resolved = base / p
    parts: list[str] = []
    for part in resolved.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts) if parts else None
