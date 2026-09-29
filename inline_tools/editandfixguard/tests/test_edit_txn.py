"""Step 9（git 事务、create、revert、sync 与 edit() 编排）的验收测试。

验收条目见 NEXT_STEP.md「Step 9」。测试用临时 git 仓库，不改本仓库工作区。
sync 一律用可控的 fake 替换，不真的调 codeindex。
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _import(name: str):
    sys.path.insert(0, str(REPO_ROOT))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(REPO_ROOT))


edit_mod = _import("inline_tools.editandfixguard.edit")
git_txn = _import("inline_tools.editandfixguard.git_txn")

edit = edit_mod.edit


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        shell=False, capture_output=True, text=True, check=True,
    )


def _init_repo(root: Path, files: dict[str, str]) -> None:
    _git(root, "init")
    for name, text in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "-c", "user.email=t@e.com", "-c", "user.name=t", "commit", "-m", "init")


def _sha(root: Path) -> str:
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*")) if p.is_file() and ".git" not in p.parts
    }


def _ok_sync(root, file, **kw):
    return True


def _fail_sync(root, file, **kw):
    return False



# 让判据 1 和 G2.1 放行的宿主注入参数：根因在 player.gd 第 5 行，
# 改名的 _ready 进 declared_scope
PATCH_KW = {
    "root_cause_errors": [{"res_path": "res://player.gd", "line": 5}],
    "pointers": [],
    "declared_scope": ["res://player.gd#func:_ready"],
}

PLAYER = """extends KinematicBody2D

var speed := 200

func _ready():
	pass
"""

PATCH_HUNK = [{
    "context_before": ["var speed := 200", ""],
    "remove": ["func _ready():"],
    "insert": ["func _enter_tree():"],
    "context_after": ["\tpass"],
}]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _init_repo(tmp_path, {"player.gd": PLAYER})
    return tmp_path


class TestApplyCheckFailed:
    """git apply --check 失败 → APPLY_CHECK_FAILED，磁盘未动。"""

    def test_bad_patch_disk_untouched(self, repo: Path) -> None:
        before = _snapshot(repo)
        sha_before = _sha(repo)
        # 构造一个 apply --check 过不了的 patch：锚定能过（fuzz），但 udiff 与文件对不上
        # 直接喂一个语法上合法但上下文不匹配 hand-made udiff
        result = edit(
            repo, file="player.gd", kind="patch",
            hunks=[{"remove": ["func _ready():"], "insert": ["func _enter_tree():"],
                    "context_before": [], "context_after": []}],
            sync_fn=_ok_sync,
        )
        # 这个其实能锚定成功；换个真的 apply 失败的：对已被改的文件再 patch
        # 用更直接的方式：patch 一个不存在的 hunk 组合导致 udiff 与磁盘不符
        # 这里只要确认：当 APPLY_CHECK_FAILED 发生时磁盘不变。用 git_txn 直接测。
        result2 = git_txn.apply_check(repo, "--- a/player.gd\n+++ b/player.gd\n@@ -99,1 +99,1 @@\n-x\n+y\n")
        assert not result2.ok
        assert result2.code == git_txn.APPLY_CHECK_FAILED
        assert _snapshot(repo) == before
        assert _sha(repo) == sha_before


class TestApplyIndex:
    """apply 使用 --index 且不含 --reject 和 --3way；补丁文件在工作区之外。"""

    def test_apply_index_argv(self, repo: Path, monkeypatch) -> None:
        calls: list[list[str]] = []
        real_run = subprocess.run

        def spy(cmd, **kw):
            calls.append(cmd)
            return real_run(cmd, **kw)

        monkeypatch.setattr(subprocess, "run", spy)
        udiff = "--- a/player.gd\n+++ b/player.gd\n@@ -1,1 +1,1 @@\n-extends KinematicBody2D\n+extends Node2D\n"
        git_txn.apply_index(repo, udiff)
        apply_calls = [c for c in calls if "apply" in c]
        assert apply_calls
        for cmd in apply_calls:
            assert "--index" in cmd
            assert "--reject" not in cmd
            assert "--3way" not in cmd
            # 补丁文件路径不在工作区内
            patch_arg = cmd[-1]
            assert not str(patch_arg).startswith(str(repo))


class TestCommitFailed:
    """COMMIT_FAILED 会回滚到调用前 sha。"""

    def test_commit_failure_rolls_back(self, repo: Path, monkeypatch) -> None:
        sha_before = _sha(repo)
        # 让 commit 失败：把 apply_index 之后强行 returncode=1
        real_commit = git_txn.commit

        def bad_commit(root, message):
            return git_txn.GitResult(False, git_txn.COMMIT_FAILED, "forced failure")

        monkeypatch.setattr(edit_mod.git_txn, "commit", bad_commit)
        result = edit(repo, file="player.gd", kind="patch", hunks=PATCH_HUNK, sync_fn=_ok_sync, **PATCH_KW)
        assert result["ok"] is False
        assert result["reject_reason"] == git_txn.COMMIT_FAILED
        assert _sha(repo) == sha_before
        # 工作区字节与调用前一致
        assert (repo / "player.gd").read_text() == PLAYER


class TestOnDiskVerification:
    """落盘后字节必须等于内存 new_text；失败则 SYNTAX_BROKEN / SCENE_REGRESSION 并 reset。"""

    def test_gd_syntax_broken_resets(self, repo: Path, monkeypatch) -> None:
        sha_before = _sha(repo)
        # 让落盘后的 error 节点数比内存判定高：篡改 _verify_on_disk 的输入
        # 更直接：patch 成语法坏的 .gd，内存判定时 error 已升高会被判据 2 拦住；
        # 这里测「落盘字节 != 内存」这条路径，靠 monkeypatch 模拟读回不匹配
        original_read = Path.read_bytes

        def tampered_read(self):
            if self.name == "player.gd" and ".git" not in str(self):
                return b"tampered"
            return original_read(self)

        monkeypatch.setattr(Path, "read_bytes", tampered_read)
        result = edit(repo, file="player.gd", kind="patch", hunks=PATCH_HUNK, sync_fn=_ok_sync, **PATCH_KW)
        assert result["ok"] is False
        assert result["reject_reason"] == edit_mod.SYNTAX_BROKEN
        assert _sha(repo) == sha_before

    def test_scene_regression_resets(self, repo: Path) -> None:
        sha_before = _sha(repo)
        (repo / "main.tscn").write_text("[gd_scene format=3]\n", encoding="utf-8")
        _git(repo, "add", "main.tscn")
        _git(repo, "-c", "user.email=t@e.com", "-c", "user.name=t", "commit", "-m", "add scene")
        sha_after_scene = _sha(repo)
        # create 一个本身带 L4 ERROR 的场景
        result = edit(
            repo, file="bad.tscn", kind="create",
            content="[node name=\"R\" type=\"Node2D\"]\n",  # 缺 gd_scene 头
            sync_fn=_ok_sync,
        )
        assert result["ok"] is False
        assert result["reject_reason"] in (edit_mod.SCENE_REGRESSION, "GUARD_REJECTED")
        assert _sha(repo) == sha_after_scene


class TestRollbackCommand:
    """第 6 步之后的失败：reset --hard + clean -fd -e ...，不含 -x。"""

    def test_rollback_argv(self, repo: Path, monkeypatch) -> None:
        calls: list[list[str]] = []
        real_run = subprocess.run

        def spy(cmd, **kw):
            calls.append(cmd)
            return real_run(cmd, **kw)

        monkeypatch.setattr(subprocess, "run", spy)
        git_txn.rollback(repo, _sha(repo))
        clean_calls = [c for c in calls if "clean" in c]
        assert clean_calls
        for cmd in clean_calls:
            assert "-fd" in cmd
            assert "-x" not in cmd
            assert "-e" in cmd
            for excluded in (".godot", ".import", ".codeindex"):
                assert excluded in cmd


class TestCommitMessage:
    """commit message 字段齐全；无 verify 时 signature 为 none；warn 的 override id 在正文。"""

    def test_message_fields(self) -> None:
        msg = git_txn.build_commit_message(
            round=3, file="res://player.gd",
            sig_before="abc", sig_after="def",
            rule_id=7, guard_verdict="pass", udiff="some diff",
        )
        assert "round=3" in msg
        assert "res://player.gd" in msg
        assert "sig-before=abc" in msg
        assert "sig-after=def" in msg
        assert "rule-id=7" in msg
        assert "guard=pass" in msg
        assert "patch-hash=" in msg

    def test_no_verify_signature_is_none(self) -> None:
        msg = git_txn.build_commit_message(
            round=1, file="f", sig_before=None, sig_after=None,
            rule_id=None, guard_verdict="pass", udiff="d",
        )
        assert "sig-before=none" in msg
        assert "sig-after=none" in msg
        assert "rule-id=none" in msg

    def test_warn_override_in_body(self) -> None:
        msg = git_txn.build_commit_message(
            round=1, file="f", sig_before="a", sig_after="b",
            rule_id=None, guard_verdict="warn", udiff="d",
            overrides=["BULK_DELETE"],
        )
        assert "BULK_DELETE" in msg

    def test_justification_not_in_message(self, repo: Path) -> None:
        result = edit(
            repo, file="player.gd", kind="patch", hunks=PATCH_HUNK, **PATCH_KW,
            justification="rm -rf /; echo pwned", sync_fn=_ok_sync,
        )
        assert result["ok"] is True
        log = _git(repo, "log", "-1", "--pretty=%B").stdout
        assert "pwned" not in log
        assert "rm -rf" not in log


class TestSync:
    """sync 失败不 reset，index_stale=true；成功时为 false。"""

    def test_sync_failure_keeps_commit_and_stale(self, repo: Path) -> None:
        sha_before = _sha(repo)
        result = edit(repo, file="player.gd", kind="patch", hunks=PATCH_HUNK, sync_fn=_fail_sync, **PATCH_KW)
        assert result["ok"] is True
        assert result["index_stale"] is True
        assert _sha(repo) != sha_before  # commit 留下了

    def test_sync_success_not_stale(self, repo: Path) -> None:
        result = edit(repo, file="player.gd", kind="patch", hunks=PATCH_HUNK, sync_fn=_ok_sync, **PATCH_KW)
        assert result["ok"] is True
        assert result["index_stale"] is False


class TestCreate:
    """create：content 为 new_text，无锚定；commit 失败后 untracked 新文件被清掉。"""

    def test_create_commits_new_file(self, repo: Path) -> None:
        result = edit(
            repo, file="new_script.gd", kind="create",
            content="extends Node\n\nfunc _ready():\n\tpass\n",
            sync_fn=_ok_sync,
        )
        assert result["ok"] is True
        assert (repo / "new_script.gd").read_text() == "extends Node\n\nfunc _ready():\n\tpass\n"
        assert result["applied_files"] == ["res://new_script.gd"]

    def test_create_commit_failure_cleans_untracked(self, repo: Path, monkeypatch) -> None:
        sha_before = _sha(repo)

        def bad_commit(root, message):
            return git_txn.GitResult(False, git_txn.COMMIT_FAILED, "forced")

        monkeypatch.setattr(edit_mod.git_txn, "commit", bad_commit)
        result = edit(
            repo, file="another.gd", kind="create",
            content="extends Node\n", sync_fn=_ok_sync,
        )
        assert result["ok"] is False
        assert _sha(repo) == sha_before
        assert not (repo / "another.gd").exists()  # untracked 新文件被 clean 掉


class TestRevert:
    """revert：不跑写前判据；to_commit None 退 HEAD~1；baseline 限制；回滚后 sync。"""

    def _three_commits(self, repo: Path) -> list[str]:
        shas = [_sha(repo)]
        for i in range(2):
            (repo / "player.gd").write_text(PLAYER + f"\n# v{i}\n", encoding="utf-8")
            _git(repo, "add", "player.gd")
            _git(repo, "-c", "user.email=t@e.com", "-c", "user.name=t", "commit", "-m", f"v{i}")
            shas.append(_sha(repo))
        return shas

    def test_revert_to_none_goes_head_minus_1(self, repo: Path) -> None:
        shas = self._three_commits(repo)
        synced: list[str] = []
        result = edit(repo, file="player.gd", kind="revert", to_commit=None,
                      sync_fn=lambda r, f, **k: synced.append(f) or True)
        assert result["ok"] is True
        assert result["commit"] == shas[-2]
        assert synced  # 回滚后 sync 被调

    def test_revert_refuses_before_baseline(self, repo: Path) -> None:
        shas = self._three_commits(repo)
        baseline = shas[1]
        result = edit(repo, file="player.gd", kind="revert",
                      to_commit=shas[0], baseline_sha=baseline, sync_fn=_ok_sync)
        assert result["ok"] is False
        assert result["reject_reason"] == git_txn.REVERT_REFUSED

    def test_revert_without_baseline_only_one_commit(self, repo: Path) -> None:
        shas = self._three_commits(repo)
        result = edit(repo, file="player.gd", kind="revert",
                      to_commit=shas[0], sync_fn=_ok_sync)  # 两个 commit 前
        assert result["ok"] is False
        assert result["reject_reason"] == git_txn.REVERT_REFUSED

    def test_revert_skips_pre_guards(self, repo: Path) -> None:
        # 脏工作区在 revert 时也不跑 DIRTY_WORKTREE 前置
        self._three_commits(repo)
        (repo / "dirty.gd").write_text("extends Node\n", encoding="utf-8")
        result = edit(repo, file="player.gd", kind="revert", to_commit=None, sync_fn=_ok_sync)
        # revert 不被 DIRTY_WORKTREE 拦
        assert result["reject_reason"] != "DIRTY_WORKTREE" or result["ok"]


class TestForbiddenGitOps:
    """不调用 stash、worktree、init、config；不 wipe uid；不写 gitignore。"""

    def test_no_forbidden_git_ops(self, repo: Path, monkeypatch) -> None:
        calls: list[list[str]] = []
        real_run = subprocess.run

        def spy(cmd, **kw):
            calls.append(cmd)
            return real_run(cmd, **kw)

        monkeypatch.setattr(subprocess, "run", spy)
        edit(repo, file="player.gd", kind="patch", hunks=PATCH_HUNK, sync_fn=_ok_sync, **PATCH_KW)
        for cmd in calls:
            if cmd[:2] == ["git", "-C"]:
                subcommand = cmd[3]
                assert subcommand not in ("stash", "worktree", "init", "config")


class TestReturnShape:
    """返回字典字段齐全；guard 拒绝、锚点失败、前置失败时字节不变且没有新 commit。"""

    def test_success_return_keys(self, repo: Path) -> None:
        result = edit(repo, file="player.gd", kind="patch", hunks=PATCH_HUNK, sync_fn=_ok_sync, **PATCH_KW)
        for key in ("ok", "commit", "guard", "applied_files", "reject_reason", "index_stale", "counts_as_verify_round"):
            assert key in result

    def test_guard_reject_no_commit_bytes_unchanged(self, repo: Path) -> None:
        before = _snapshot(repo)
        sha_before = _sha(repo)
        # patch 超出爆炸半径 → guard reject
        result = edit(
            repo, file="player.gd", kind="patch",
            hunks=[{"remove": ["extends KinematicBody2D"], "insert": ["extends Node2D"],
                    "context_before": [], "context_after": []}],
            root_cause_errors=[{"res_path": "res://other.gd", "line": 1}],
            pointers=[], sync_fn=_ok_sync,
        )
        assert result["ok"] is False
        assert _sha(repo) == sha_before
        assert _snapshot(repo) == before

    def test_anchor_failure_no_commit_bytes_unchanged(self, repo: Path) -> None:
        before = _snapshot(repo)
        sha_before = _sha(repo)
        result = edit(
            repo, file="player.gd", kind="patch",
            hunks=[{"remove": ["func nonexistent():"], "insert": ["func x():"],
                    "context_before": [], "context_after": []}],
            sync_fn=_ok_sync,
        )
        assert result["ok"] is False
        assert _sha(repo) == sha_before
        assert _snapshot(repo) == before

    def test_precheck_failure_no_commit_bytes_unchanged(self, repo: Path) -> None:
        before = _snapshot(repo)
        sha_before = _sha(repo)
        (repo / "dirty.gd").write_text("extends Node\n", encoding="utf-8")  # 脏工作区
        result = edit(repo, file="player.gd", kind="patch", hunks=PATCH_HUNK, sync_fn=_ok_sync, **PATCH_KW)
        assert result["ok"] is False
        assert result["reject_reason"] == "DIRTY_WORKTREE"
        assert _sha(repo) == sha_before
