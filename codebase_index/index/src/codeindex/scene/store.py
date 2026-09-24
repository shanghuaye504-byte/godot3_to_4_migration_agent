"""L3：把场景模型写入已有的 SQLite 事务。

由 writer.reindex_batch 在同一个事务里调用。本模块自己不 commit。
写入或删除 scene_* 行。不往 files 表插 .tscn / .tres。
含 NUL 记 BINARY，单文件超过 4MB 记 SKIPPED_OVERSIZE。
单个场景失败只记 MALFORMED，不把整批事务弄回滚。
解析 res://、相对路径和 :: 后缀。只有 uid、没有 path 时 resolved_file 为空。

契约见 codebase_index/NEXT_STEP.md 第 4 节。
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path, PurePosixPath

from codeindex.scene.model import parse_scene
from codeindex.scene.resolve import SceneModel, resolve

# 与官方 converter 静默跳过的门槛对齐（NEXT_STEP 4.1）。
_OVERSIZE_BYTES = 4 * 1024 * 1024


def store_scene(
    conn: sqlite3.Connection,
    abs_path: Path,
    rel: str,
    project_root: Path,
) -> str:
    """在调用方已经打开的事务里写入一个 .tscn / .tres。

    返回 'reindexed' | 'skipped' | 'failed'，给 writer 计数用。
    本函数不 commit / rollback；单个场景失败只记 MALFORMED，不往上抛。
    """
    if not abs_path.exists():
        _delete_scene(conn, rel)
        return "reindexed"

    raw = abs_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    mtime = int(abs_path.stat().st_mtime)

    # hash 短路：与库中一致则跳过
    row = conn.execute(
        "SELECT sha FROM scene_files WHERE path = ?", (rel,)
    ).fetchone()
    if row is not None and row[0] == sha:
        return "skipped"

    # 二进制：含 NUL 不当文本解析
    if b"\x00" in raw:
        _replace_scene_file(
            conn, rel, sha, mtime,
            doc_kind=None, fmt=None, uid=None, script_class=None,
            parse_status="BINARY", problem_count=0, root_count=0, is_inherited=0,
        )
        return "reindexed"

    # 超限
    if len(raw) > _OVERSIZE_BYTES:
        _replace_scene_file(
            conn, rel, sha, mtime,
            doc_kind=None, fmt=None, uid=None, script_class=None,
            parse_status="SKIPPED_OVERSIZE", problem_count=0, root_count=0, is_inherited=0,
        )
        return "reindexed"

    text = raw.decode("utf-8", errors="replace")
    try:
        doc = parse_scene(text, rel)
        model = resolve(doc)
    except Exception:
        _replace_scene_file(
            conn, rel, sha, mtime,
            doc_kind=None, fmt=None, uid=None, script_class=None,
            parse_status="MALFORMED", problem_count=0, root_count=0, is_inherited=0,
        )
        return "reindexed"

    parse_status = "OK" if not doc.problems else "MALFORMED"
    _replace_scene_file(
        conn, rel, sha, mtime,
        doc_kind=doc.doc_kind, fmt=doc.format, uid=doc.uid,
        script_class=doc.script_class,
        parse_status=parse_status, problem_count=len(doc.problems),
        root_count=len(model.root_paths),
        is_inherited=1 if model.is_inherited else 0,
    )
    _insert_model(conn, rel, model, project_root)
    return "reindexed"


def _delete_scene(conn: sqlite3.Connection, rel: str) -> None:
    """删掉该 path 在全部 scene_* 表中的行。"""
    for table in (
        "scene_files", "scene_nodes", "scene_ext", "scene_sub",
        "scene_conn", "scene_refs",
    ):
        conn.execute(f"DELETE FROM {table} WHERE path = ?", (rel,))


def _replace_scene_file(
    conn: sqlite3.Connection,
    rel: str,
    sha: str,
    mtime: int,
    *,
    doc_kind: str | None,
    fmt: int | None,
    uid: str | None,
    script_class: str | None,
    parse_status: str,
    problem_count: int,
    root_count: int,
    is_inherited: int,
) -> None:
    """先清旧行再插新行。BINARY / SKIPPED_OVERSIZE / MALFORMED 也走这里。"""
    _delete_scene(conn, rel)
    conn.execute(
        "INSERT INTO scene_files "
        "(path, doc_kind, format, uid, script_class, sha, mtime, parse_status, "
        " problem_count, root_count, is_inherited, indexed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            rel, doc_kind, fmt, uid, script_class, sha, mtime, parse_status,
            problem_count, root_count, is_inherited, int(time.time()),
        ),
    )


def _insert_model(
    conn: sqlite3.Connection,
    rel: str,
    model: SceneModel,
    project_root: Path,
) -> None:
    """把 SceneModel 的节点、资源、连接、引用边写进 scene_* 表。"""
    # 实例子树弃权前缀集合
    unresolved = set(model.unresolved_subtrees)

    for node in model.nodes:
        in_unresolved = _in_unresolved(node.node_path, unresolved)
        script_ext_id = _find_call_id(node, model, "script_ref")
        instance_ext_id = _find_call_id(node, model, "instance")
        conn.execute(
            "INSERT INTO scene_nodes "
            "(path, node_path, name, type, parent_path, script_ext_id, "
            " instance_ext_id, is_placeholder, in_unresolved_subtree, line) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                rel, node.node_path, node.name, node.type, node.parent,
                script_ext_id, instance_ext_id,
                1 if node.has_instance_placeholder else 0,
                1 if in_unresolved else 0,
                node.heading_span.line,
            ),
        )

    for ext in model.ext.values():
        resolved = _resolve_ref_path(ext.ref_path, rel, project_root)
        conn.execute(
            "INSERT INTO scene_ext "
            "(path, ext_id, type, uid, ref_path, resolved_file, line) "
            "VALUES (?,?,?,?,?,?,?)",
            (rel, ext.id, ext.type, ext.uid, ext.ref_path, resolved, ext.span.line),
        )

    for sub in model.sub.values():
        conn.execute(
            "INSERT INTO scene_sub (path, sub_id, type, line) VALUES (?,?,?,?)",
            (rel, sub.id, sub.type, sub.span.line),
        )

    for c in model.conns:
        conn.execute(
            "INSERT INTO scene_conn "
            "(path, signal, from_path, to_path, method, line) "
            "VALUES (?,?,?,?,?,?)",
            (rel, c.signal, c.from_path, c.to_path, c.method, c.span.line),
        )

    for ref in model.refs:
        target_file = _ref_target_file(ref, model, project_root, rel)
        detail = _ref_detail(ref)
        conn.execute(
            "INSERT INTO scene_refs "
            "(path, line, col, kind, symbol, node_path, target_file, detail) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                rel, ref.span.line, ref.span.col, ref.kind, ref.value,
                ref.node_path, target_file, detail,
            ),
        )


def _in_unresolved(node_path: str, unresolved: set[str]) -> bool:
    """node_path 是否落在某个实例子树前缀下。"""
    for prefix in unresolved:
        if prefix == ".":
            return True
        if node_path == prefix or node_path.startswith(prefix + "/"):
            return True
    return False


def _find_call_id(node, model: SceneModel, kind: str) -> str | None:
    """在 refs 里找这个节点的 script_ref / instance 对应的 ext id。"""
    for ref in model.refs:
        if ref.kind == kind and ref.node_path == node.node_path:
            return ref.value
    return None


def _resolve_ref_path(
    ref_path: str | None,
    current_rel: str,
    project_root: Path,
) -> str | None:
    """ref_path → resolved_file（相对 project_root 的 posix 路径）。

    按 NEXT_STEP 4.4：
      1. 去掉 ::SubName 后缀
      2. res://X → X（相对 project_root）
      3. 相对路径 → dirname(当前文件) / X
      4. 只有 uid://、没有 path → None
      5. 全失败 → None
    返回 None 表示解析不到（文件不存在也算解析不到，因为本层不读磁盘存在性，
    只算路径；存在性由 L4 判）。
    """
    if ref_path is None:
        return None
    # 去 :: 后缀
    path = ref_path.split("::")[0]
    if not path:
        return None
    if path.startswith("res://"):
        return path[6:]
    if path.startswith("uid://"):
        return None
    # 相对路径：落到当前 .tscn 所在目录
    base = PurePosixPath(current_rel).parent
    resolved = base / path
    # 规范化 .. 和 .
    parts: list[str] = []
    for part in resolved.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts) if parts else None


def _ref_target_file(
    ref,
    model: SceneModel,
    project_root: Path,
    current_rel: str,
) -> str | None:
    """script_ref / ext_path / instance 的 target_file。"""
    if ref.kind == "script_ref":
        ext = model.ext.get(ref.value)
        if ext is not None and ext.ref_path is not None:
            return _resolve_ref_path(ext.ref_path, current_rel, project_root)
    elif ref.kind == "ext_path":
        return _resolve_ref_path(ref.value, current_rel, project_root)
    elif ref.kind == "instance":
        ext = model.ext.get(ref.value)
        if ext is not None and ext.ref_path is not None:
            return _resolve_ref_path(ext.ref_path, current_rel, project_root)
    return None


def _ref_detail(ref) -> str | None:
    """给 find-symbol 展示用的原文片段。"""
    if ref.kind == "node_type":
        return f'type="{ref.value}"'
    if ref.kind == "res_type":
        return f'type="{ref.value}"'
    if ref.kind == "script_ref":
        return f"script = ExtResource({ref.value})"
    if ref.kind == "instance":
        return f"instance = ExtResource({ref.value})"
    if ref.kind == "conn_method":
        return f'method="{ref.value}"'
    if ref.kind == "conn_signal":
        return f'signal="{ref.value}"'
    if ref.kind == "ext_path":
        return f'path="{ref.value}"'
    if ref.kind == "group":
        return f'groups=["{ref.value}"]'
    if ref.kind == "nodepath":
        return f'NodePath("{ref.value}")'
    if ref.kind == "prop_key":
        return ref.value
    if ref.kind == "script_class":
        return f'script_class="{ref.value}"'
    return None
