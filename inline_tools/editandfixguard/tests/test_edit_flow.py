"""Step 10 端到端：合法 patch / 判据 4 拒绝 / warn 各一次。

验收条目见 NEXT_STEP.md「Step 10 串起来」。用临时 git 仓库，不改本仓库工作区。
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


def _status(root: Path) -> str:
    return _git(root, "status", "--porcelain").stdout.strip()


def _ok_sync(root, file, **kw):
    return True


PLAYER = """extends KinematicBody2D

var speed := 200

func _ready():
	pass
"""

# 判据 1 / G2.1 放行参数：根因在 player.gd 第 5 行，_ready 改名进 declared_scope
PATCH_KW = {
    "root_cause_errors": [{"res_path": "res://player.gd", "line": 5}],
    "pointers": [],
    "declared_scope": ["res://player.gd#func:_ready"],
}

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


class TestCleanPatch:
    """一次合法 patch：commit 出现，工作区 clean，message 字段齐全，verdict=pass。"""

    def test_clean_patch_end_to_end(self, repo: Path) -> None:
        sha_before = _sha(repo)
        result = edit(
            repo, file="player.gd", kind="patch", hunks=PATCH_HUNK,
            round=3, sig_before="sig-b", sig_after="sig-a", rule_id=7,
            sync_fn=_ok_sync, **PATCH_KW,
        )
        assert result["ok"] is True
        # commit 出现
        assert result["commit"] is not None
        assert _sha(repo) != sha_before
        # 工作区 clean
        assert _status(repo) == ""
        # verdict=pass
        assert result["guard"]["verdict"] == "pass"
        # message 字段齐全
        message = _git(repo, "log", "-1", "--pretty=%B").stdout
        assert "round=3" in message
        assert "res://player.gd" in message
        assert "sig-before=sig-b" in message
        assert "sig-after=sig-a" in message
        assert "rule-id=7" in message
        assert "guard=pass" in message
        assert "patch-hash=" in message


class TestLazyReject:
    """一次判据 4 拒绝：无 commit，文件字节不变，counts_as_verify_round=false。"""

    def test_lazy_pass_rejected(self, repo: Path) -> None:
        sha_before = _sha(repo)
        bytes_before = (repo / "player.gd").read_bytes()
        # 把 _ready 的函数体从一行 pass 改成两行 pass → 新增的整行 pass 触发判据 4
        result = edit(
            repo, file="player.gd", kind="patch",
            hunks=[{
                "context_before": ["", "func _ready():"],
                "remove": ["\tpass"],
                "insert": ["\tpass\n\tpass"],
                "context_after": [],
            }],
            sync_fn=_ok_sync, **PATCH_KW,
        )
        assert result["ok"] is False
        assert result["reject_reason"] == "GUARD_REJECTED"
        ids = [v["id"] for v in result["guard"]["violations"]]
        assert "LAZY_PASS" in ids
        # 无 commit，字节不变
        assert _sha(repo) == sha_before
        assert (repo / "player.gd").read_bytes() == bytes_before
        assert result["counts_as_verify_round"] is False


class TestWarnFlow:
    """一次 warn（TODO）：有 commit，verdict=warn，violations 与 override 都在返回值和 message 里。"""

    def test_todo_warn_end_to_end(self, repo: Path) -> None:
        sha_before = _sha(repo)
        # 改 speed 并加 TODO 注释 → 判据 4 LAZY_TODO warn
        result = edit(
            repo, file="player.gd", kind="patch",
            hunks=[{
                "context_before": [""],
                "remove": ["var speed := 200"],
                "insert": ["var speed := 300  # TODO: tune later"],
                "context_after": [""],
            }],
            round=1, sig_before="s1", sig_after="s2", rule_id=None,
            root_cause_errors=[{"res_path": "res://player.gd", "line": 3}],
            pointers=[], sync_fn=_ok_sync,
        )
        assert result["ok"] is True
        assert _sha(repo) != sha_before  # 有 commit
        assert result["guard"]["verdict"] == "warn"
        # violations 在返回值里
        ids = [v["id"] for v in result["guard"]["violations"]]
        assert "LAZY_TODO" in ids
        # message 里有 guard=warn
        message = _git(repo, "log", "-1", "--pretty=%B").stdout
        assert "guard=warn" in message

    def test_bulk_delete_warn_override_in_result_and_message(self, repo: Path) -> None:
        # INCONSISTENT_RENAME 需要场景文件；用 allow_bulk_delete 的 warn + override 路径
        # 构造一个 G4.1 被豁免 + G4.2 warn 的 patch
        # 100 行注释（不是符号，G2.1 不拦），删 50 行 → G4.1 豁免 + G4.2 warn
        big = "\n".join(f"# comment line {i}" for i in range(1, 101)) + "\n"
        (repo / "big.gd").write_text(big, encoding="utf-8")
        _git(repo, "add", "big.gd")
        _git(repo, "-c", "user.email=t@e.com", "-c", "user.name=t", "commit", "-m", "add big")
        sha_before = _sha(repo)

        remove = [f"# comment line {i}" for i in range(1, 51)]
        result = edit(
            repo, file="big.gd", kind="patch",
            hunks=[{"context_before": [], "remove": remove, "insert": ["# collapsed"], "context_after": []}],
            round=2, sig_before="a", sig_after="b", rule_id=None,
            root_cause_errors=[{"res_path": "res://big.gd", "line": 1}],
            pointers=[], allow_bulk_delete=True, sync_fn=_ok_sync,
        )
        assert result["ok"] is True
        assert _sha(repo) != sha_before
        assert result["guard"]["verdict"] == "warn"
        # violations 与 override 都在返回值里
        ids = [v["id"] for v in result["guard"]["violations"]]
        assert "DELETION_RATIO" in ids
        assert "BULK_DELETE" in result["guard"]["overrides"]
        # message 里有 override id
        message = _git(repo, "log", "-1", "--pretty=%B").stdout
        assert "guard=warn" in message
        assert "BULK_DELETE" in message
