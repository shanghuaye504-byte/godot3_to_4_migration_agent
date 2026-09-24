"""grep 工具的验收测试。

验收条目见 inline_tools/grep/ARCHITECTURE.md 第 7 节。
"""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

import pytest

# 与 test_read.py 相同：先插入仓根，确保 inline_tools 包解析自单一位置。
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_WS = Path(__file__).parent / "fixtures" / "workspace"


def _import_grep():
    sys.path.insert(0, str(REPO_ROOT))
    try:
        return importlib.import_module("inline_tools.grep")
    finally:
        sys.path.remove(str(REPO_ROOT))


grep_mod = _import_grep()


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    """从 fixtures/workspace 拷贝到 tmp_path 的工作区，避免直接污染 fixture。"""
    shutil.copytree(FIXTURE_WS, tmp_path, dirs_exist_ok=True)
    return tmp_path


class TestSearchMode:
    """验收 1/8：有 pattern 时，结果带 res:// 路径、1-based line、与文件一致的 text；
    能命中 .tscn 正文（当前索引不覆盖该后缀）。"""

    def test_match_carries_res_path_line_and_text(self, ws: Path) -> None:
        result = grep_mod.grep(ws, pattern="KinematicBody2D")
        assert result["ok"] is True
        assert result["files_only"] is False

        scene_hit = next(
            match for match in result["matches"] if match["path"].endswith(".tscn")
        )
        assert scene_hit["path"] == "res://levels/l1.tscn"
        assert scene_hit["line"] == 5
        assert scene_hit["text"] == '[node name="Player" type="KinematicBody2D"]'

    def test_context_within_hard_cap(self, ws: Path) -> None:
        # 工作区里 "velocity" 仅在 player.gd 第 6 行；要求 context=1 时
        # 前后各 1 行（虽然硬上限是 5，req=1 时窗口只有 1），可验证窗口按请求执行。
        result = grep_mod.grep(ws, pattern="velocity", context=1)
        assert result["ok"] is True
        hit = result["matches"][0]
        assert hit["path"] == "res://player.gd"
        assert hit["context_before"] == ["func _ready():"]
        assert hit["context_after"] == []  # 文件末尾，没有 after


class TestFilesOnlyMode:
    """验收 2：pattern 为空时 files_only=true，结果只有路径，没有行号。"""

    def test_empty_pattern_lists_files_matching_glob(self, ws: Path) -> None:
        result = grep_mod.grep(ws, glob="*.tscn")
        assert result["ok"] is True
        assert result["files_only"] is True
        assert [match["path"] for match in result["matches"]] == [
            "res://levels/l1.tscn"
        ]
        for match in result["matches"]:
            assert "line" not in match and "text" not in match

    def test_empty_pattern_lists_all_files(self, ws: Path) -> None:
        result = grep_mod.grep(ws)
        paths = {match["path"] for match in result["matches"]}
        assert "res://levels/l1.tscn" in paths
        assert "res://player.gd" in paths
        # 禁止目录下的文件不能出现
        assert not any(".godot" in path for path in paths)


class TestTruncation:
    """验收 3：超过 max_results 时 truncated=true；传入大于 500 的 max_results
    时返回条数仍不超过 500。"""

    def test_results_truncated_at_max_results(self, ws: Path) -> None:
        # 工作区里有两个命中，max_results=1 触发截断
        result = grep_mod.grep(ws, pattern="KinematicBody2D", max_results=1)
        assert result["ok"] is True
        assert result["truncated"] is True
        assert len(result["matches"]) == 1
        # total_matches 报告截断前数量
        assert result["total_matches"] >= 2

    def test_hard_cap_at_500(self, tmp_path: Path) -> None:
        for index in range(600):
            (tmp_path / f"file{index:03d}.gd").write_text(
                "extends Node\n", encoding="utf-8"
            )
        result = grep_mod.grep(tmp_path, pattern="extends", max_results=999)
        assert result["ok"] is True
        assert len(result["matches"]) <= 500


class TestContextCap:
    """验收 4：context 大于 5 时按 5 截断，不把更大窗口返回出去。"""

    def test_context_hard_capped_at_five(self, tmp_path: Path) -> None:
        lines = "\n".join(f"line{i}" for i in range(20)) + "\nkeyword line\n"
        (tmp_path / "long.gd").write_text(lines, encoding="utf-8")
        result = grep_mod.grep(tmp_path, pattern="keyword", context=99)
        assert result["ok"] is True
        hit = result["matches"][0]
        assert len(hit["context_before"]) <= 5
        assert len(hit["context_after"]) <= 5


class TestForbiddenAndEscape:
    """验收 5：禁止目录与越界路径都返回结构化错误码，不是空命中。"""

    def test_forbidden_directory_in_path_is_rejected(self, ws: Path) -> None:
        result = grep_mod.grep(ws, pattern="x", path=".godot")
        assert result["ok"] is False
        assert result["error"]["code"] == "PATH_FORBIDDEN"

    def test_path_escape_is_rejected(self, ws: Path) -> None:
        result = grep_mod.grep(ws, pattern="x", path="../outside")
        assert result["ok"] is False
        assert result["error"]["code"] == "PATH_ESCAPE"

    def test_forbidden_dir_never_appears_in_results(self, ws: Path) -> None:
        # .godot 下有 "KinematicBody2D"，但结果不能包含它
        result = grep_mod.grep(ws, pattern="KinematicBody2D")
        assert result["ok"] is True
        assert all(".godot" not in match["path"] for match in result["matches"])


class TestArgvSafety:
    """验收 6：pattern 含 shell 元字符时仍只是 -e 的一个参数，不经过 shell。"""

    def test_shell_metachars_are_literal(self, ws: Path) -> None:
        # 如果走 shell，分号会导致多条命令，结果不可预期；字面化时 rg
        # 找不到 "pass; done" 就正常返回空命中
        result = grep_mod.grep(ws, pattern="pass; done")
        assert result["ok"] is True
        assert result["matches"] == []


class TestWorkspaceUnchanged:
    """验收 7：调用前后工作区字节不变（只读通道）。"""

    def test_workspace_bytes_unchanged(self, ws: Path) -> None:
        before = {
            path.relative_to(ws): path.read_bytes()
            for path in ws.rglob("*")
            if path.is_file()
        }
        grep_mod.grep(ws, pattern="KinematicBody2D")
        after = {
            path.relative_to(ws): path.read_bytes()
            for path in ws.rglob("*")
            if path.is_file()
        }
        assert before == after


class TestSearchWithoutHitsIsSuccess:
    """搜索无命中是成功：matches 空、total_matches=0、truncated=False。"""

    def test_zero_hits_is_success(self, ws: Path) -> None:
        result = grep_mod.grep(ws, pattern="no_such_symbol_zzz")
        assert result["ok"] is True
        assert result["matches"] == []
        assert result["total_matches"] == 0
        assert result["truncated"] is False
