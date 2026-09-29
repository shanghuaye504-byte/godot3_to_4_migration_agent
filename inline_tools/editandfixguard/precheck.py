"""流水线第 0 步前置：git 状态、路径、文本性检查。

行为依据 NEXT_STEP.md「Step 1 第 0 步前置」与「不许自行解释的约定」。
路径解析复用 `inline_tools._workspace.resolve_workspace_path`，本模块只在它
之上追加本包自己的拒绝：`.git`、`*.uid`、`*.import`、白名单外后缀。

本步只读：任何分支都不写盘、不执行 `git init`。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from .._workspace import WorkspaceError, resolve_workspace_path

# 稳定错误码
NOT_A_GIT_REPO = "NOT_A_GIT_REPO"
DIRTY_WORKTREE = "DIRTY_WORKTREE"
PATH_ESCAPE = "PATH_ESCAPE"
PATH_FORBIDDEN = "PATH_FORBIDDEN"
NOT_TEXT = "NOT_TEXT"

# 扩展名白名单（「不许自行解释的约定」：白名单外一律 PATH_FORBIDDEN）
ALLOWED_SUFFIXES = frozenset({".gd", ".tscn", ".tres", ".gdshader", ".godot", ".cfg"})

# 文本性上限：超过即 NOT_TEXT
MAX_TEXT_BYTES = 4 * 1024 * 1024


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """只读 git 调用。argv 列表、shell=False；本步只允许 status / rev-parse。"""
    return subprocess.run(
        ["git", "-C", str(root), *args],
        shell=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _check_suffix(res_rel: str) -> str | None:
    """白名单外后缀、*.uid、*.import → PATH_FORBIDDEN；通过返回 None。"""
    name = res_rel.rsplit("/", 1)[-1]
    if name.endswith(".uid") or name.endswith(".import"):
        return PATH_FORBIDDEN
    suffix = name.rsplit(".", 1)[-1] if "." in name else ""
    if f".{suffix}" not in ALLOWED_SUFFIXES:
        return PATH_FORBIDDEN
    return None


def precheck(
    project_root: str | os.PathLike[str],
    path: str,
) -> dict[str, Any]:
    """第 0 步前置：git 仓库、干净工作区、路径、文本性。

    参数：
        project_root: 宿主注入的工作区根目录。
        path: ``res://...`` 或相对 project_root 的目标文件路径。

    通过返回 ``{"ok": True, "path", "base_sha"}``，``base_sha`` 为调用时的
    ``HEAD`` sha。失败返回 ``{"ok": False, "error": {"code", "message"}}``。
    任何失败分支都不写盘。
    """
    root = Path(os.path.realpath(Path(project_root).expanduser()))

    # 1. 必须是 git 仓库；只探测，绝不 git init
    probe = _git(root, "rev-parse", "--is-inside-work-tree")
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return _error(NOT_A_GIT_REPO, f"not a git repository: {root}")

    # 2. 工作区必须干净；脏工作区不写盘
    status = _git(root, "status", "--porcelain")
    if status.returncode != 0:
        return _error(NOT_A_GIT_REPO, f"git status failed: {status.stderr.strip()}")
    if status.stdout.strip():
        return _error(DIRTY_WORKTREE, "working tree has uncommitted changes")

    # 3. 路径解析：逃逸与禁止目录沿用 _workspace 的约定
    try:
        absolute, res_rel = resolve_workspace_path(root, path)
    except WorkspaceError as exc:
        return _error(exc.code, exc.message)

    # 4. 本包追加的禁止项：.git 任何分量、*.uid、*.import、白名单外后缀
    rel = absolute.relative_to(root)
    if ".git" in rel.parts:
        return _error(PATH_FORBIDDEN, f"path under .git: {path!r}")
    suffix_error = _check_suffix(res_rel)
    if suffix_error is not None:
        return _error(suffix_error, f"suffix not allowed: {path!r}")

    # 5. 文本性：NUL、大于 4MB、非 UTF-8 → NOT_TEXT（文件不存在时不拦，
    #    create 的 old_text 为空由后续步骤处理，本步只对已存在的文件判文本性）
    if absolute.exists():
        data = absolute.read_bytes()
        if len(data) > MAX_TEXT_BYTES:
            return _error(NOT_TEXT, f"file larger than 4MB: {path!r}")
        if b"\x00" in data:
            return _error(NOT_TEXT, f"file contains NUL byte: {path!r}")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return _error(NOT_TEXT, f"file is not valid UTF-8: {path!r}")

    # 6. 通过：记下 HEAD sha
    head = _git(root, "rev-parse", "HEAD")
    if head.returncode != 0:
        return _error(NOT_A_GIT_REPO, f"git rev-parse HEAD failed: {head.stderr.strip()}")
    return {"ok": True, "path": res_rel, "base_sha": head.stdout.strip()}
