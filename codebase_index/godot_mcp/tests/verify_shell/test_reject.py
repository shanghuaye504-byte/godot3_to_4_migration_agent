"""入队拒收：`.csproj` / `.gdextension` 要拦，`.godot` 里的同后缀不管。"""

from __future__ import annotations

from pathlib import Path

import pytest

from godot_mcp.verify_shell.reject import (
    UnsupportedProjectError,
    find_unsupported_files,
    reject_if_unsupported,
)


def test_clean_gdscript_project_passes(tmp_path: Path) -> None:
    (tmp_path / "player.gd").write_text("extends Node\n", encoding="utf-8")
    assert find_unsupported_files(tmp_path) == []
    reject_if_unsupported(tmp_path)


def test_csproj_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "Game.csproj").write_text("<Project/>\n", encoding="utf-8")
    with pytest.raises(UnsupportedProjectError, match="C#"):
        reject_if_unsupported(tmp_path)


def test_ignores_files_inside_godot(tmp_path: Path) -> None:
    hidden = tmp_path / ".godot" / "dummy.csproj"
    hidden.parent.mkdir()
    hidden.write_text("<Project/>\n", encoding="utf-8")
    assert find_unsupported_files(tmp_path) == []
