"""read 工具的验收测试。

验收条目见 inline_tools/read/ARCHITECTURE.md 第 5 节。
"""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

import pytest

# pytest 把 tests 目录加入 sys.path；为从仓根导入 inline_tools 包，避免
# sys.path 顺序歧义，先插入仓根再导入。
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_WS = Path(__file__).parent / "fixtures" / "workspace"


def _import_read():
    sys.path.insert(0, str(REPO_ROOT))
    try:
        return importlib.import_module("inline_tools.read")
    finally:
        sys.path.remove(str(REPO_ROOT))


read_mod = _import_read()

PLAYER_LINES = [
    "extends KinematicBody2D",
    "",
    "var speed := 200",
    "",
    "func _ready():",
    "\tvelocity = Vector2.ZERO",
]


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    """从 fixtures/workspace 拷贝到 tmp_path 的最小工作区，避免直接污染 fixture。"""
    shutil.copytree(FIXTURE_WS, tmp_path, dirs_exist_ok=True)
    return tmp_path


class TestSliceSemantics:
    """验收 1：行区间语义 —— 请求 2–4 行时 n 依次为 2、3、4，text 与原文逐字一致。"""

    def test_slice_has_absolute_line_numbers(self, ws: Path) -> None:
        result = read_mod.read(ws, "player.gd", line_from=2, line_to=4)
        assert result["ok"] is True
        assert [line["n"] for line in result["lines"]] == [2, 3, 4]
        assert [line["text"] for line in result["lines"]] == [
            PLAYER_LINES[1],
            PLAYER_LINES[2],
            PLAYER_LINES[3],
        ]

    def test_slice_preserves_indentation(self, ws: Path) -> None:
        # GDScript 缩进敏感：tab 必须逐字保留，否则后续锚定编辑对不上
        result = read_mod.read(ws, "player.gd", line_from=6, line_to=6)
        assert result["lines"][0]["text"] == "\tvelocity = Vector2.ZERO"


class TestLongFileTruncation:
    """验收 2：超过 2000 行且 line_to 为空时，返回 2000 行，truncated=true。"""

    def test_long_file_returns_first_2000_lines(self, tmp_path: Path) -> None:
        big = tmp_path / "big.gd"
        big.write_text("".join(f"line{i}\n" for i in range(1, 5001)), encoding="utf-8")
        result = read_mod.read(tmp_path, "big.gd")
        assert result["ok"] is True
        assert result["truncated"] is True
        assert len(result["lines"]) == 2000
        assert result["total_lines"] == 5000


class TestRejections:
    """验收 3/4/5：结构化错误码，不伪装空切片。"""

    def test_file_not_found(self, ws: Path) -> None:
        result = read_mod.read(ws, "missing.gd")
        assert result["ok"] is False
        assert result["error"]["code"] == "FILE_NOT_FOUND"

    def test_path_escape_is_rejected(self, ws: Path) -> None:
        result = read_mod.read(ws, "../outside.gd")
        assert result["ok"] is False
        assert result["error"]["code"] == "PATH_ESCAPE"

    @pytest.mark.parametrize("blocked_dir", [".godot", ".import", ".codeindex"])
    def test_forbidden_directory_is_rejected(self, ws: Path, blocked_dir: str) -> None:
        forbidden = ws / blocked_dir / "cache.gd"
        forbidden.parent.mkdir(exist_ok=True)
        forbidden.write_text("extends Node\n", encoding="utf-8")
        result = read_mod.read(ws, f"{blocked_dir}/cache.gd")
        assert result["ok"] is False
        assert result["error"]["code"] == "PATH_FORBIDDEN"

    def test_bad_range_rejected(self, ws: Path) -> None:
        assert read_mod.read(ws, "player.gd", line_from=0)["error"]["code"] == "BAD_RANGE"
        reversed_range = read_mod.read(ws, "player.gd", line_from=4, line_to=2)
        assert reversed_range["error"]["code"] == "BAD_RANGE"


class TestPathEquivalence:
    """验收 6：res:// 与相对路径等价。"""

    def test_res_scheme_matches_relative(self, ws: Path) -> None:
        via_res = read_mod.read(ws, "res://player.gd")
        via_rel = read_mod.read(ws, "player.gd")
        assert via_res["ok"] is True and via_rel["ok"] is True
        assert via_res["lines"] == via_rel["lines"]
        assert via_res["path"] == "res://player.gd"


class TestWorkspaceUnchanged:
    """验收 7：调用前后字节不变（只读通道）。"""

    def test_read_does_not_modify_file(self, ws: Path) -> None:
        player = ws / "player.gd"
        digest_before = player.read_bytes()
        read_mod.read(ws, "player.gd")
        assert player.read_bytes() == digest_before
