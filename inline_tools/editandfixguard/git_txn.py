"""git 事务：apply --check / apply --index / commit / 失败回滚 / revert。

行为依据 NEXT_STEP.md「Step 9」与「不许自行解释的约定」。
git 一律 argv 列表、shell=False。不调用 `git stash`、`git worktree`、
`git init`、`git config`；不 wipe `*.uid`；不写 `.gitignore`。
补丁写在被测工作区之外的临时文件。commit 带 `--no-verify`。
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

# 稳定错误码
APPLY_CHECK_FAILED = "APPLY_CHECK_FAILED"
COMMIT_FAILED = "COMMIT_FAILED"
REVERT_REFUSED = "REVERT_REFUSED"

# 第 6 步之后失败的清理命令里 clean 的豁免项
_CLEAN_EXCLUDES = [".godot", ".import", ".codeindex"]


@dataclass(frozen=True)
class GitResult:
    ok: bool
    code: str | None = None
    message: str = ""
    sha: str | None = None


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        shell=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def head_sha(root: Path) -> str:
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def patch_hash(udiff: str) -> str:
    return hashlib.sha1(udiff.encode()).hexdigest()


def apply_check(root: Path, udiff: str) -> GitResult:
    """`git apply --check`，补丁文件在工作区之外。失败时磁盘未动。"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".patch", delete=False, dir=tempfile.gettempdir()
    ) as handle:
        handle.write(udiff)
        patch_path = handle.name
    result = _git(root, "apply", "--check", patch_path)
    if result.returncode != 0:
        return GitResult(False, APPLY_CHECK_FAILED, result.stderr.strip())
    return GitResult(True)


def apply_index(root: Path, udiff: str) -> GitResult:
    """`git apply --index`；不含 `--reject`、不含 `--3way`；补丁在工作区之外。"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".patch", delete=False, dir=tempfile.gettempdir()
    ) as handle:
        handle.write(udiff)
        patch_path = handle.name
    result = _git(root, "apply", "--index", patch_path)
    if result.returncode != 0:
        return GitResult(False, APPLY_CHECK_FAILED, result.stderr.strip())
    return GitResult(True)


def build_commit_message(
    *,
    round: object,
    file: str,
    sig_before: str | None,
    sig_after: str | None,
    rule_id: object,
    guard_verdict: str,
    udiff: str,
    overrides: list[str] | None = None,
) -> str:
    """服务端拼接 commit message；justification 不进入 argv。

    无 verify 时 signature 为 ``none``；warn 的 override id 写进正文。
    """
    sig_before = sig_before or "none"
    sig_after = sig_after or "none"
    lines = [
        f"[edit] round={round} file={file}",
        f"sig-before={sig_before} sig-after={sig_after}",
        f"rule-id={rule_id if rule_id is not None else 'none'} guard={guard_verdict}",
        f"patch-hash={patch_hash(udiff)}",
    ]
    if overrides:
        lines.append(f"overrides={','.join(overrides)}")
    return "\n".join(lines)


def commit(root: Path, message: str) -> GitResult:
    """`git commit --no-verify`。message 走 stdin 之外的安全通道：-m 列表参数。"""
    result = _git(root, "commit", "--no-verify", "-m", message)
    if result.returncode != 0:
        return GitResult(False, COMMIT_FAILED, result.stderr.strip())
    return GitResult(True, sha=head_sha(root))


def rollback(root: Path, base_sha: str) -> None:
    """第 6 步之后的失败：reset --hard + clean -fd（豁免缓存目录，不含 -x）。"""
    _git(root, "reset", "--hard", base_sha)
    args = ["clean", "-fd"]
    for exclude in _CLEAN_EXCLUDES:
        args += ["-e", exclude]
    _git(root, *args)


def revert(root: Path, *, to_commit: str | None, baseline_sha: str | None, current_sha: str) -> GitResult:
    """`kind=revert` 的 git 侧：退到 to_commit（None 时 HEAD~1）。

    有 baseline_sha 时拒绝退到 baseline 之前；未传入 baseline 时只允许退一个
    commit（即 to_commit 必须解析为 HEAD~1）。
    """
    target = to_commit or "HEAD~1"
    if baseline_sha is not None:
        # 拒绝退到 baseline 之前：target 必须是 baseline 的后代
        ahead = _git(root, "merge-base", "--is-ancestor", baseline_sha, target)
        if ahead.returncode != 0:
            return GitResult(False, REVERT_REFUSED, f"target {target} is before baseline")
    elif to_commit is not None:
        # 未传 baseline：只允许退一个 commit
        if _git(root, "rev-parse", to_commit).stdout.strip() != _git(root, "rev-parse", "HEAD~1").stdout.strip():
            return GitResult(False, REVERT_REFUSED, "only one commit back is allowed without baseline")

    result = _git(root, "reset", "--hard", target)
    if result.returncode != 0:
        return GitResult(False, COMMIT_FAILED, result.stderr.strip())
    return GitResult(True, sha=head_sha(root))
