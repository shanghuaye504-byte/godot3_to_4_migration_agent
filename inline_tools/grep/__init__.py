"""grep：在工作区里按固定参数调用 rg——要么搜索文本，要么列文件。

签名与边界见 grep/ARCHITECTURE.md。底层是固定参数的 rg，参数以 argv 列表
传递，不经过 shell，模型给的 pattern 不会被解释成管道或重定向。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from .._workspace import (
    PATH_ESCAPE,
    WorkspaceError,
    resolve_project_root,
    resolve_workspace_path,
)

# 上限，见 grep/ARCHITECTURE.md 第 4 节
DEFAULT_MAX_RESULTS = 100
HARD_MAX_RESULTS = 500
HARD_MAX_CONTEXT = 5

# rg 进程超时的兜底：搜索不应无限挂住
SUBPROCESS_TIMEOUT_S = 30

# 稳定错误码
BAD_LIMIT = "BAD_LIMIT"
RG_NOT_FOUND = "RG_NOT_FOUND"
RG_FAILED = "RG_FAILED"

_EXCLUDE_ARGS = [
    "-g", "!.godot/**",
    "-g", "!.import/**",
    "-g", "!.codeindex/**",
]


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


def _find_rg() -> str | None:
    """定位 rg 可执行文件。优先 PATH，其次常见的独立安装位置。"""
    found = shutil.which("rg")
    if found:
        return found
    # ripgrep-all / codex 自带的 rg 常见位置（本仓库开发机即如此）
    candidates = [
        "/opt/homebrew/bin/rg",
        "/usr/local/bin/rg",
        os.path.expanduser("~/.cargo/bin/rg"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _run_rg(argv: list[str], cwd: str) -> tuple[int, str, str]:
    """以 argv 列表方式启动 rg，返回 (returncode, stdout, stderr)。不经过 shell。"""
    proc = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_S,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def grep(
    project_root: str | os.PathLike[str],
    pattern: str | None = None,
    glob: str | None = None,
    path: str | None = None,
    context: int = 0,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> dict[str, Any]:
    """在工作区里搜索文本，或当 pattern 为空时列出文件。

    参数：
        project_root: 宿主注入的工作区根目录。
        pattern: 搜索串。None 或空字符串表示不搜内容，只列文件。
        glob: 传给 ``rg -g`` 的过滤，如 ``"*.tscn"``。
        path: 可选子树，res:// 或相对路径。None 表示整个工作区。
        context: 命中行前后各带几行，默认 0，硬上限 5。
        max_results: 最多返回几条，默认 100，硬上限 500。
    """
    # 调用错误：不返回空成功
    if max_results < 1:
        return _error(BAD_LIMIT, f"max_results must be >= 1, got {max_results}")
    if context < 0:
        return _error(BAD_LIMIT, f"context must be >= 0, got {context}")

    effective_max = min(max_results, HARD_MAX_RESULTS)
    effective_context = min(context, HARD_MAX_CONTEXT)

    root = resolve_project_root(project_root)

    # 子树限定：与 read 共用同一套工作区路径规则
    search_root = root
    if path is not None:
        try:
            resolved_path, _ = resolve_workspace_path(project_root, path)
        except WorkspaceError as exc:
            return _error(exc.code, exc.message)
        if not resolved_path.exists():
            # 子树不存在按 PATH_ESCAPE 语义处理：模型给了一个不在工作区里的位置
            return _error(PATH_ESCAPE, f"path does not exist: {path!r}")
        search_root = resolved_path

    rg_bin = _find_rg()
    if rg_bin is None:
        return _error(RG_NOT_FOUND, "ripgrep (rg) executable not found")

    files_only = pattern is None or pattern == ""

    argv = [rg_bin]
    if files_only:
        argv += ["--files"]
    else:
        argv += ["--json"]
    argv += _EXCLUDE_ARGS
    if glob is not None:
        argv += ["-g", glob]
    if not files_only:
        argv += ["-C", str(effective_context), "-e", pattern]
    argv.append(".")

    try:
        returncode, stdout, stderr = _run_rg(argv, cwd=str(search_root))
    except subprocess.TimeoutExpired:
        return _error(RG_FAILED, "rg timed out")

    # rg 退出码：0=有命中，1=无命中，>=2=错误
    if returncode not in (0, 1):
        return _error(RG_FAILED, f"rg exited {returncode}: {stderr.strip()}")

    if files_only:
        return _parse_files(stdout, root, search_root, effective_max)
    return _parse_matches(stdout, root, search_root, effective_max)


def _to_res_rel(file_path: str, root, search_root) -> str:
    """把 rg 输出的相对路径规范成 res:// 形式。

    rg 在 search_root 下以相对路径输出（因为 argv 最后是 "."），先拼回
    search_root，再相对 project_root 取 rel。
    """
    absolute = (search_root / file_path).resolve()
    rel = absolute.relative_to(root)
    return "res://" + "/".join(rel.parts)


def _parse_files(stdout: str, root, search_root, effective_max: int) -> dict[str, Any]:
    """列文件模式：rg --files 每行一个相对路径。"""
    paths = [line for line in stdout.splitlines() if line]
    total = len(paths)
    truncated = total > effective_max
    shown = paths[:effective_max]
    return {
        "ok": True,
        "matches": [{"path": _to_res_rel(p, root, search_root)} for p in shown],
        "total_matches": total,
        "truncated": truncated,
        "files_only": True,
    }


def _parse_matches(stdout: str, root, search_root, effective_max: int) -> dict[str, Any]:
    """搜索模式：解析 rg --json 的 NDJSON，只收集 match 事件，并附带 context。"""
    # 先按出现顺序收集所有事件，match 事件之外还需要 context 事件补前后文
    events: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    matches: list[dict[str, Any]] = []
    # pending_context_before: 尚未归属到某个 match 的 context 行（按文件分组暂存）
    pending_before: dict[str, list[str]] = {}
    last_match_index: int | None = None

    def _file_key(data: dict[str, Any]) -> str:
        return data["path"]["text"]

    for event in events:
        kind = event.get("type")
        data = event.get("data", {})
        if kind == "match":
            key = _file_key(data)
            entry = {
                "path": _to_res_rel(key, root, search_root),
                "line": data["line_number"],
                "text": data["lines"]["text"].rstrip("\r\n"),
                "context_before": pending_before.pop(key, []),
                "context_after": [],
            }
            matches.append(entry)
            last_match_index = len(matches) - 1
        elif kind == "context":
            key = _file_key(data)
            text = data["lines"]["text"].rstrip("\r\n")
            # 如果上一个事件是同文件的 match，这段 context 是它的 after；
            # 否则暂存为下一个 match 的 before。
            if (
                last_match_index is not None
                and matches[last_match_index]["path"]
                == _to_res_rel(key, root, search_root)
                and not pending_before.get(key)
            ):
                matches[last_match_index]["context_after"].append(text)
            else:
                pending_before.setdefault(key, []).append(text)

    total = len(matches)
    truncated = total > effective_max
    shown = matches[:effective_max]
    return {
        "ok": True,
        "matches": shown,
        "total_matches": total,
        "truncated": truncated,
        "files_only": False,
    }


__all__ = ["grep", "DEFAULT_MAX_RESULTS", "HARD_MAX_RESULTS", "HARD_MAX_CONTEXT"]
