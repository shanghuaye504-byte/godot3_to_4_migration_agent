"""precheck（流水线第 0 步前置）的验收测试。

验收条目见 NEXT_STEP.md「Step 1 第 0 步前置」。测试直接调用
`inline_tools.editandfixguard.precheck.precheck`，不经过尚未实现的 edit()。
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _import_precheck():
    sys.path.insert(0, str(REPO_ROOT))
    try:
        return importlib.import_module("inline_tools.editandfixguard.precheck")
    finally:
        sys.path.remove(str(REPO_ROOT))


precheck_mod = _import_precheck()
precheck = precheck_mod.precheck


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        shell=False,
        capture_output=True,
        text=True,
        check=True,
    )


def _git_maybe(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        shell=False,
        capture_output=True,
        text=True,
    )


def _init_repo(root: Path) -> None:
    """建一个已提交一个文件的干净 git 仓库。"""
    _git(root, "init")
    _git(root, "-c", "user.email=test@example.com", "-c", "user.name=test",
         "commit", "--allow-empty", "-m", "init")


def _snapshot(root: Path) -> dict[str, bytes]:
    """工作区全部文件（含 .git）的字节快照，用于断言失败时磁盘不变。"""
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """干净 git 仓库，内含一个已提交的 player.gd。"""
    (tmp_path / "player.gd").write_text("extends Node\n", encoding="utf-8")
    _init_repo(tmp_path)
    _git(tmp_path, "add", "player.gd")
    _git(tmp_path, "-c", "user.email=test@example.com", "-c", "user.name=test",
         "commit", "-m", "add player")
    return tmp_path


class TestNotAGitRepo:
    """非 git 仓库 → NOT_A_GIT_REPO，且不执行 git init。"""

    def test_plain_directory_is_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "player.gd").write_text("extends Node\n", encoding="utf-8")
        result = precheck(tmp_path, "player.gd")
        assert result["ok"] is False
        assert result["error"]["code"] == "NOT_A_GIT_REPO"

    def test_does_not_run_git_init(self, tmp_path: Path) -> None:
        (tmp_path / "player.gd").write_text("extends Node\n", encoding="utf-8")
        precheck(tmp_path, "player.gd")
        assert not (tmp_path / ".git").exists()


class TestDirtyWorktree:
    """git status --porcelain 非空 → DIRTY_WORKTREE，不写盘。"""

    def test_uncommitted_change_is_rejected(self, repo: Path) -> None:
        (repo / "player.gd").write_text("extends Node2D\n", encoding="utf-8")
        result = precheck(repo, "player.gd")
        assert result["ok"] is False
        assert result["error"]["code"] == "DIRTY_WORKTREE"

    def test_untracked_file_is_rejected(self, repo: Path) -> None:
        (repo / "new_file.gd").write_text("extends Node\n", encoding="utf-8")
        result = precheck(repo, "player.gd")
        assert result["error"]["code"] == "DIRTY_WORKTREE"

    def test_dirty_worktree_does_not_write(self, repo: Path) -> None:
        target = repo / "player.gd"
        target.write_text("extends Node2D\n", encoding="utf-8")
        before = _snapshot(repo)
        precheck(repo, "player.gd")
        assert _snapshot(repo) == before


class TestPathEscape:
    """../、绝对路径、symlink 穿出 → PATH_ESCAPE。"""

    def test_dotdot_is_rejected(self, repo: Path) -> None:
        result = precheck(repo, "../outside.gd")
        assert result["error"]["code"] == "PATH_ESCAPE"

    def test_absolute_path_is_rejected(self, repo: Path) -> None:
        result = precheck(repo, str(repo / "player.gd"))
        assert result["error"]["code"] == "PATH_ESCAPE"

    def test_symlink_escape_is_rejected(self, repo: Path, tmp_path_factory) -> None:
        outside = tmp_path_factory.mktemp("outside")
        (outside / "secret.gd").write_text("extends Node\n", encoding="utf-8")
        link = repo / "link"
        link.symlink_to(outside, target_is_directory=True)
        _git(repo, "add", "link")
        _git(repo, "-c", "user.email=test@example.com", "-c", "user.name=test",
             "commit", "-m", "add symlink")
        result = precheck(repo, "link/secret.gd")
        assert result["error"]["code"] == "PATH_ESCAPE"


class TestPathForbidden:
    """.godot/ .import/ .codeindex/ .git/、*.uid、*.import、白名单外后缀 → PATH_FORBIDDEN。"""

    @pytest.mark.parametrize("blocked_dir", [".godot", ".import", ".codeindex"])
    def test_forbidden_directories(self, repo: Path, blocked_dir: str) -> None:
        result = precheck(repo, f"{blocked_dir}/cache.gd")
        assert result["error"]["code"] == "PATH_FORBIDDEN"

    def test_dot_git_is_rejected(self, repo: Path) -> None:
        result = precheck(repo, ".git/HEAD")
        assert result["error"]["code"] == "PATH_FORBIDDEN"

    def test_uid_suffix_is_rejected(self, repo: Path) -> None:
        result = precheck(repo, "player.gd.uid")
        assert result["error"]["code"] == "PATH_FORBIDDEN"

    def test_import_suffix_is_rejected(self, repo: Path) -> None:
        result = precheck(repo, "icon.png.import")
        assert result["error"]["code"] == "PATH_FORBIDDEN"

    @pytest.mark.parametrize("name", ["icon.png", "data.bin", "notes.md", "archive.zip"])
    def test_suffix_outside_whitelist_is_rejected(self, repo: Path, name: str) -> None:
        result = precheck(repo, name)
        assert result["error"]["code"] == "PATH_FORBIDDEN"


class TestSuffixWhitelist:
    """白名单仅 .gd .tscn .tres .gdshader .godot .cfg：这些后缀不被 PATH_FORBIDDEN 拦。"""

    @pytest.mark.parametrize(
        "name",
        ["a.gd", "a.tscn", "a.tres", "a.gdshader", "project.godot", "a.cfg"],
    )
    def test_whitelisted_suffixes_pass_path_check(self, repo: Path, name: str) -> None:
        (repo / name).write_text("extends Node\n", encoding="utf-8")
        _git(repo, "add", name)
        _git(repo, "-c", "user.email=test@example.com", "-c", "user.name=test",
             "commit", "-m", f"add {name}")
        result = precheck(repo, name)
        assert result["ok"] is True, result


class TestNotText:
    """NUL、大于 4MB、非 UTF-8 → NOT_TEXT。"""

    def _commit(self, repo: Path, name: str) -> None:
        _git(repo, "add", name)
        _git(repo, "-c", "user.email=test@example.com", "-c", "user.name=test",
             "commit", "-m", f"add {name}")

    def test_nul_byte_is_rejected(self, repo: Path) -> None:
        (repo / "bad.gd").write_bytes(b"extends Node\n\x00\n")
        self._commit(repo, "bad.gd")
        result = precheck(repo, "bad.gd")
        assert result["error"]["code"] == "NOT_TEXT"

    def test_larger_than_4mb_is_rejected(self, repo: Path) -> None:
        (repo / "big.gd").write_bytes(b"a" * (4 * 1024 * 1024 + 1))
        self._commit(repo, "big.gd")
        result = precheck(repo, "big.gd")
        assert result["error"]["code"] == "NOT_TEXT"

    def test_non_utf8_is_rejected(self, repo: Path) -> None:
        (repo / "latin.gd").write_bytes("extends Node\n# caf\xe9\n".encode("latin-1"))
        self._commit(repo, "latin.gd")
        result = precheck(repo, "latin.gd")
        assert result["error"]["code"] == "NOT_TEXT"


class TestPassReturnsHeadSha:
    """通过时返回 HEAD sha。"""

    def test_ok_returns_head_sha(self, repo: Path) -> None:
        expected = _git(repo, "rev-parse", "HEAD").stdout.strip()
        result = precheck(repo, "player.gd")
        assert result["ok"] is True
        assert result["base_sha"] == expected
        assert result["path"] == "res://player.gd"

    def test_res_scheme_matches_relative(self, repo: Path) -> None:
        via_res = precheck(repo, "res://player.gd")
        via_rel = precheck(repo, "player.gd")
        assert via_res["ok"] is True and via_rel["ok"] is True
        assert via_res["path"] == via_rel["path"] == "res://player.gd"
        assert via_res["base_sha"] == via_rel["base_sha"]


class TestWorkspaceUnchanged:
    """以上失败磁盘字节不变。"""

    def test_failed_precheck_leaves_disk_untouched(self, repo: Path) -> None:
        before = _snapshot(repo)
        for bad_path in ["../x.gd", "/abs/x.gd", ".git/HEAD", "a.png", "a.gd.uid"]:
            assert precheck(repo, bad_path)["ok"] is False
        assert _snapshot(repo) == before
        assert _git_maybe(repo, "status", "--porcelain").stdout.strip() == ""
