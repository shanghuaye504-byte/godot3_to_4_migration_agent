"""edit() 编排：流水线第 0–11 步。

行为依据 NEXT_STEP.md「Step 9」与各判据 Step。一次 `edit` 只改一个 `file`；
`kind` 只有 `patch`、`create`、`revert`。模型可见字段只有设计书 schema 里的
那些；宿主注入 `project_root` / `round` / `root_cause_errors` / `pointers` /
`sig_before` / `sig_after` / `baseline_sha`。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from . import anchor, git_txn, guard, precheck, scene_names, symbols, sync_index

# 稳定错误码（本层新增）
SYNTAX_BROKEN = "SYNTAX_BROKEN"
SCENE_REGRESSION = "SCENE_REGRESSION"

_TEXT_SUFFIXES = {".gd", ".tscn", ".tres"}
_GD = ".gd"
_SCENE = {".tscn", ".tres"}


def _fail(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "commit": None,
        "guard": None,
        "applied_files": [],
        "reject_reason": code,
        "index_stale": False,
        "counts_as_verify_round": False,
        **extra,
    }


def edit(
    project_root: str | os.PathLike[str],
    *,
    file: str,
    kind: str,
    hunks: list[dict[str, Any]] | None = None,
    content: str | None = None,
    to_commit: str | None = None,
    justification: str | None = None,
    allow_bulk_delete: bool = False,
    declared_scope: list[str] | None = None,
    rule_id: Any = None,
    # 宿主注入
    round: Any = None,
    root_cause_errors: list[dict[str, Any]] | None = None,
    pointers: list[dict[str, Any]] | None = None,
    sig_before: str | None = None,
    sig_after: str | None = None,
    baseline_sha: str | None = None,
    rules_db_path: Path | None = None,
    db_path: Path | None = None,
    # 测试可替换 sync
    sync_fn=sync_index.sync_file,
) -> dict[str, Any]:
    root = Path(project_root)

    # ---------- revert：不跑写前判据 ----------
    if kind == "revert":
        return _revert(
            root, file=file, to_commit=to_commit, baseline_sha=baseline_sha, sync_fn=sync_fn
        )

    # ---------- 第 0 步：前置 ----------
    pre = precheck.precheck(root, file)
    if not pre["ok"]:
        return _fail(pre["error"]["code"], pre["error"]["message"])
    base_sha = pre["base_sha"]
    res_file = pre["path"]
    suffix = Path(res_file).suffix

    # ---------- create ----------
    if kind == "create":
        new_text = content or ""
        old_text = ""
        udiff = _create_udiff(res_file, new_text)
        anchor_warnings: list[str] = []
    else:
        # ---------- patch：读旧文本 + 锚定 ----------
        old_text = (root / res_file[len("res://"):]).read_text(encoding="utf-8")
        hunk_objs = [anchor.Hunk(**h) for h in (hunks or [])]
        anchored = anchor.apply_hunks(old_text, hunk_objs)
        if not anchored["ok"]:
            err = anchored["error"]
            return _fail(err["code"], err["message"], guard={"candidates": err.get("candidates")})
        new_text = anchored["new_text"]
        udiff = anchored["udiff"].replace("b/file", f"b/{res_file[len('res://'):]}").replace(
            "a/file", f"a/{res_file[len('res://'):]}"
        )
        anchor_warnings = anchored["warnings"]

    # ---------- 写前判据 ----------
    # create 不跑判据 1–4（没有旧文本可比，爆炸半径/偷懒修复无意义）；
    # 场景文件仍跑场景不变量（新文件自身的问题视为回归）。
    guard_results: list[Any] = []
    if suffix == _GD and kind != "create":
        guard_results.append(guard.check_blast_radius(
            udiff,
            root_cause_errors=root_cause_errors or [],
            pointers=pointers or [],
            declared_scope=declared_scope,
            rule_id=rule_id,
            rules_db_path=rules_db_path,
            file_texts={res_file: old_text},
        ))
        guard_results.append(symbols.check_symbols(
            res_file, old_text, new_text,
            declared_scope=declared_scope, rules_db_path=rules_db_path,
        ))
        guard_results.append(guard.check_deletion(
            udiff, file=res_file, old_text=old_text, new_text=new_text,
            allow_bulk_delete=allow_bulk_delete,
        ))
        guard_results.append(guard.check_lazy_fix(udiff, file=res_file))
    elif suffix in _SCENE:
        guard_results.append(scene_names.check_scene_invariants(res_file, old_text, new_text))

    verdict = guard.verdict(*guard_results, anchor_warnings=anchor_warnings)
    if verdict["verdict"] == "reject":
        return _fail(
            "GUARD_REJECTED", "guard rejected",
            guard=verdict,
        )

    # ---------- 第 5 步：apply --check ----------
    checked = git_txn.apply_check(root, udiff)
    if not checked.ok:
        return _fail(checked.code, checked.message, guard=verdict)

    # ---------- 第 6 步：apply --index ----------
    applied = git_txn.apply_index(root, udiff)
    if not applied.ok:
        git_txn.rollback(root, base_sha)
        return _fail(applied.code, applied.message, guard=verdict)

    # ---------- 第 7 步：落盘后复核 ----------
    broken = _verify_on_disk(root, res_file, new_text, suffix)
    if broken is not None:
        git_txn.rollback(root, base_sha)
        return _fail(broken, "on-disk verification failed", guard=verdict)

    # ---------- 第 8 步：commit ----------
    message = git_txn.build_commit_message(
        round=round, file=res_file,
        sig_before=sig_before, sig_after=sig_after,
        rule_id=rule_id, guard_verdict=verdict["verdict"],
        udiff=udiff, overrides=verdict["overrides"],
    )
    committed = git_txn.commit(root, message)
    if not committed.ok:
        git_txn.rollback(root, base_sha)
        return _fail(committed.code, committed.message, guard=verdict)

    # ---------- 第 10 步：sync（失败不 reset）----------
    index_stale = not sync_fn(root, res_file)

    return {
        "ok": True,
        "commit": committed.sha,
        "guard": verdict,
        "applied_files": [res_file],
        "reject_reason": None,
        "index_stale": index_stale,
        "counts_as_verify_round": verdict["counts_as_verify_round"],
    }


def _create_udiff(res_file: str, new_text: str) -> str:
    rel = res_file[len("res://"):]
    # splitlines(keepends) 保留行尾换行；git apply 会按这些行原样落盘，
    # 字节才能与内存 new_text 完全一致
    lines = new_text.splitlines(keepends=True)
    body = "".join(f"+{line.rstrip(chr(10))}\n" for line in lines)
    return f"--- /dev/null\n+++ b/{rel}\n@@ -0,0 +1,{len(lines)} @@\n{body}"


def _verify_on_disk(root: Path, res_file: str, new_text: str, suffix: str) -> str | None:
    """落盘后读回的字节必须等于内存 new_text；.gd error 节点不得升高；
    .tscn/.tres 再跑 check_scene。失败返回错误码，否则 None。"""
    on_disk = (root / res_file[len("res://"):]).read_bytes()
    if on_disk != new_text.encode():
        return SYNTAX_BROKEN if suffix == _GD else SCENE_REGRESSION
    if suffix == _GD:
        if symbols._error_node_count(on_disk.decode()) > symbols._error_node_count(new_text):
            return SYNTAX_BROKEN
    elif suffix in _SCENE:
        from codeindex.scene.rules import check_scene
        if check_scene(on_disk.decode(), res_file).problems:
            return SCENE_REGRESSION
    return None


def _revert(
    root: Path,
    *,
    file: str,
    to_commit: str | None,
    baseline_sha: str | None,
    sync_fn,
) -> dict[str, Any]:
    current = git_txn.head_sha(root)
    result = git_txn.revert(
        root, to_commit=to_commit, baseline_sha=baseline_sha, current_sha=current
    )
    if not result.ok:
        return _fail(result.code, result.message)
    index_stale = not sync_fn(root, file)
    return {
        "ok": True,
        "commit": result.sha,
        "guard": None,
        "applied_files": [file],
        "reject_reason": None,
        "index_stale": index_stale,
        "counts_as_verify_round": True,
    }
