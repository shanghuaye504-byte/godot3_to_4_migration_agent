"""场景不变量（G2.2、G2.3、G3.1）与判据 5（改名一致性）。

行为依据 NEXT_STEP.md「Step 7 场景不变量与判据 5」与「不许自行解释的约定」。
场景解析复用 `codeindex.scene.model.parse_scene` 与 `codeindex.scene.rules.check_scene`；
不把 `.tscn` / `.tres` 送进 tree-sitter，不把场景边写入 `symbols`。

判据 5 的字面量搜索复用 `inline_tools.grep`，不新起 rg 子进程。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeindex.scene.model import parse_scene
from codeindex.scene.rules import check_scene

from .. import grep as grep_mod

# 稳定 violation id
SCENE_SYNTAX_REGRESSION = "SCENE_SYNTAX_REGRESSION"      # G2.2：post 的 P_* 真包含 pre
CONFLICT_MARKER = "CONFLICT_MARKER"                      # G2.3：post 新出现冲突标记
SCENE_INVARIANT_REGRESSION = "SCENE_INVARIANT_REGRESSION"  # G3.1：post 的 L4 指纹真包含 pre
INCONSISTENT_RENAME = "INCONSISTENT_RENAME"              # 判据 5：场景仍引用旧名，warn

# 冲突标记
_CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")

# 判据 5 查 scene_refs 时限定的 kind（「不许自行解释的约定」）
_SCENE_REF_KINDS = ("conn_signal", "conn_method", "node_type", "res_type", "script_class")


@dataclass(frozen=True)
class SceneViolation:
    """一条场景判据违规。`block` 为 False 的是 warn（如 INCONSISTENT_RENAME）。"""

    id: str
    file: str
    line: int | None
    message: str
    block: bool = True


@dataclass
class SceneCheckResult:
    """G2.2 / G2.3 / G3.1 / 判据 5 的合并输出。"""

    violations: list[SceneViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(v.block for v in self.violations)


# ---------- G2.2 / G2.3 / G3.1：场景不变量 ----------


def _p_codes(text: str, path: str) -> set[str]:
    """`parse_scene` 的 P_* 语法问题码集合。"""
    return {p.code for p in parse_scene(text, path).problems}


def _l4_fingerprints(text: str, path: str) -> set[str]:
    """`check_scene` 的 L4 ERROR 指纹集合；弃权项（suppressed_checks）不计入。"""
    return {p.fingerprint for p in check_scene(text, path).problems}


def check_scene_invariants(
    file: str,
    pre_text: str,
    post_text: str,
) -> SceneCheckResult:
    """G2.2 / G2.3 / G3.1：post 相对 pre 不得新增语法问题、冲突标记、L4 ERROR。

    `create` 时 pre_text 为空：新文件自身的 error、P_*、L4 ERROR 视为回归。
    """
    result = SceneCheckResult()

    pre_p = _p_codes(pre_text, file) if pre_text else set()
    post_p = _p_codes(post_text, file)
    new_p = post_p - pre_p
    if new_p:
        result.violations.append(SceneViolation(
            id=SCENE_SYNTAX_REGRESSION, file=file, line=None,
            message=f"new scene parse problems: {sorted(new_p)}",
        ))

    pre_markers = {m for m in _CONFLICT_MARKERS if m in pre_text} if pre_text else set()
    post_markers = {m for m in _CONFLICT_MARKERS if m in post_text}
    new_markers = post_markers - pre_markers
    if new_markers:
        result.violations.append(SceneViolation(
            id=CONFLICT_MARKER, file=file, line=None,
            message=f"new conflict markers: {sorted(new_markers)}",
        ))

    pre_l4 = _l4_fingerprints(pre_text, file) if pre_text else set()
    post_l4 = _l4_fingerprints(post_text, file)
    new_l4 = post_l4 - pre_l4
    if new_l4:
        result.violations.append(SceneViolation(
            id=SCENE_INVARIANT_REGRESSION, file=file, line=None,
            message=f"new L4 errors: {len(new_l4)} fingerprint(s)",
        ))
    return result


# ---------- 判据 5：改名一致性 ----------


def _query_index(db_path: Path, names: set[str]) -> list[dict[str, Any]]:
    """在索引库里查 scene_conn.signal/method 与限定 kind 的 scene_refs.symbol。

    库不存在或打不开返回空列表（调用方据此只跑 grep，不因此拒绝）。
    """
    if not Path(db_path).is_file():
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        hits: list[dict[str, Any]] = []
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        for name in names:
            if "scene_conn" in tables:
                for row in conn.execute(
                    "SELECT path, signal, method FROM scene_conn WHERE signal = ? OR method = ?",
                    (name, name),
                ):
                    hits.append({"path": row[0], "line": None, "source": "scene_conn"})
            if "scene_refs" in tables:
                placeholders = ",".join("?" for _ in _SCENE_REF_KINDS)
                for row in conn.execute(
                    f"SELECT path, line, kind FROM scene_refs "
                    f"WHERE symbol = ? AND kind IN ({placeholders})",
                    (name, *_SCENE_REF_KINDS),
                ):
                    hits.append({"path": row[0], "line": row[1], "source": f"scene_refs.{row[2]}"})
        return hits
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def check_rename_consistency(
    project_root: str | Path,
    *,
    renamed: dict[str, str],
    db_path: Path | None = None,
) -> SceneCheckResult:
    """判据 5：.gd 上 class/func/signal 改名（不是纯删除）时，旧名不得仍被场景引用。

    `renamed` 是 ``{旧名: 新名}``。先查索引库（`db_path` 存在时），旁路表
    没覆盖到的字面量再用 `inline_tools.grep` 词边界搜 `*.tscn` / `*.tres`。
    命中 → `INCONSISTENT_RENAME`，warn，附路径和行号，不 block。索引库
    不存在时只跑 grep，不因此拒绝。
    """
    result = SceneCheckResult()
    if not renamed:
        return result

    old_names = set(renamed.keys())
    index_hits: list[dict[str, Any]] = []
    covered: set[str] = set()
    if db_path is not None:
        index_hits = _query_index(db_path, old_names)
        # 索引库可用时，它查过的名字视为已覆盖；查不到才补 grep
        if Path(db_path).is_file():
            covered = old_names

    for hit in index_hits:
        result.violations.append(SceneViolation(
            id=INCONSISTENT_RENAME,
            file=hit["path"],
            line=hit["line"],
            message=f"scene still references renamed symbol via {hit['source']}",
            block=False,
        ))

    for old_name in sorted(old_names - covered):
        for glob in ("*.tscn", "*.tres"):
            found = grep_mod.grep(
                project_root,
                pattern=rf"\b{old_name}\b",
                glob=glob,
            )
            if not found.get("ok"):
                continue
            for match in found.get("matches", []):
                result.violations.append(SceneViolation(
                    id=INCONSISTENT_RENAME,
                    file=match.get("path", ""),
                    line=match.get("line"),
                    message=f"scene file still mentions renamed symbol {old_name!r}",
                    block=False,
                ))
    return result
