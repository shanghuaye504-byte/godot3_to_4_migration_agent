"""`cache_is_warm`：只认 class cache 文件，不认空 `.godot/`。"""

from __future__ import annotations

from pathlib import Path

from godot_mcp.verify_shell.cache import CLASS_CACHE_REL, cache_is_warm


def test_missing_godot_is_cold(tmp_path: Path) -> None:
    assert cache_is_warm(tmp_path) is False


def test_empty_godot_dir_is_still_cold(tmp_path: Path) -> None:
    (tmp_path / ".godot").mkdir()
    assert cache_is_warm(tmp_path) is False


def test_class_cache_file_is_warm(tmp_path: Path) -> None:
    dest = tmp_path / CLASS_CACHE_REL
    dest.parent.mkdir(parents=True)
    dest.write_text("list=[]\n", encoding="utf-8")
    assert cache_is_warm(tmp_path) is True
