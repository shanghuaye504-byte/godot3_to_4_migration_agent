"""工作区生命周期。

从不可变 fixtures/ 复制独立副本到 workspaces/；在副本内建 git 基线用来算
workspace.diff（与 ARCHITECTURE §7 "对 fixture 副本建 git 基线看 git diff"
同构，不发明第二套 diff 机制）；实验结束删除工作区；校验原始 Fixture 文件树
hash 未变。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from . import digest

_IGNORED_DIR_NAMES = {".git", ".godot"}


class FixtureCorruptionError(Exception):
    pass


class WorkspaceSafetyError(Exception):
    pass


def _ignore_private_dirs(_dir: str, names: list[str]) -> set[str]:
    return {n for n in names if n in _IGNORED_DIR_NAMES}


def create_workspace(fixture_dir: Path, workspaces_root: Path, run_id: str, exp_id: str, group_id: str) -> Path:
    fixture_dir = Path(fixture_dir)
    workspaces_root = Path(workspaces_root)
    workspaces_root.mkdir(parents=True, exist_ok=True)
    workspace = workspaces_root / f"{run_id}-{exp_id}-{group_id}"
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(fixture_dir, workspace, ignore=_ignore_private_dirs)
    return workspace


def _git(workspace: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "-c",
            "user.name=probe-kernel",
            "-c",
            "user.email=probe@local",
            *args,
        ],
        capture_output=True,
        text=True,
        check=check,
    )


def git_init_baseline(workspace: Path) -> None:
    workspace = Path(workspace)
    gitignore = workspace / ".gitignore"
    gitignore.write_text(".godot/\n.mono/\n*.tmp\n", encoding="utf-8")
    _git(workspace, "init", "-q")
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-q", "-m", "workspace baseline", "--allow-empty")


def git_diff_since_baseline(workspace: Path) -> str:
    workspace = Path(workspace)
    stat = _git(workspace, "diff", "HEAD", "--stat", check=False).stdout
    full = _git(workspace, "diff", "HEAD", check=False).stdout
    untracked = _git(workspace, "status", "--porcelain", check=False).stdout
    return f"# stat\n{stat}\n# diff\n{full}\n# status\n{untracked}"


class DerivedPatchOutcome:
    def __init__(self, status: str, fallback_reason: Optional[str] = None):
        self.status = status
        self.fallback_reason = fallback_reason


def apply_derived_patch_if_present(workspace: Path, derived_dir: Optional[Path]) -> DerivedPatchOutcome:
    if derived_dir is None:
        return DerivedPatchOutcome(status="NOT_APPLICABLE")
    from ..hooks import apply_derived_patch as hook

    try:
        return hook.apply(workspace, Path(derived_dir))
    except NotImplementedError as exc:
        return DerivedPatchOutcome(status="NOT_IMPLEMENTED", fallback_reason=str(exc))


def verify_fixture_untouched(fixture_dir: Path, expected_hash: str) -> None:
    actual = digest.compute_tree_hash(Path(fixture_dir))
    if actual != expected_hash:
        raise FixtureCorruptionError(
            f"fixture {fixture_dir} 的文件树 hash 已变化: expected={expected_hash} actual={actual}"
        )


def destroy_workspace(workspace: Path, workspaces_root: Path) -> None:
    workspace = Path(workspace).resolve()
    workspaces_root = Path(workspaces_root).resolve()
    if workspaces_root not in workspace.parents:
        raise WorkspaceSafetyError(f"拒绝删除非 workspaces_root 下的路径: {workspace}")
    if workspace.exists():
        shutil.rmtree(workspace)


def find_probe_prefixed_leftovers(path: Path) -> list[Path]:
    path = Path(path)
    if not path.exists():
        return []
    return sorted(p for p in path.rglob("__probe_*") if p.is_file())
