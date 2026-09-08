"""`verify/sentinel.py`：哨兵脚本文本与写删契约，不起 Godot。"""

from __future__ import annotations

from pathlib import Path

from godot_mcp.verify.commands import SENTINEL_RES_PATH
from godot_mcp.verify.sentinel import (
    SENTINEL_FILENAME,
    build_sentinel_source,
    install_sentinel,
    list_gd_resources,
    remove_sentinel,
    sentinel_path,
)


def test_lists_gd_sorted_and_excludes_helpers(tmp_path: Path) -> None:
    (tmp_path / "z.gd").write_text("extends Node\n", encoding="utf-8")
    (tmp_path / "a.gd").write_text("extends Node\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "mid.gd").write_text("extends Node\n", encoding="utf-8")
    (tmp_path / SENTINEL_FILENAME).write_text("extends RefCounted\n", encoding="utf-8")
    (tmp_path / "__probe_other.gd").write_text("extends Node\n", encoding="utf-8")

    assert list_gd_resources(tmp_path) == [
        "res://a.gd",
        "res://scripts/mid.gd",
        "res://z.gd",
    ]


def test_excludes_godot_cache_scripts(tmp_path: Path) -> None:
    cache = tmp_path / ".godot" / "imported"
    cache.mkdir(parents=True)
    (cache / "ghost.gd").write_text("extends Node\n", encoding="utf-8")
    (tmp_path / "player.gd").write_text("extends Node\n", encoding="utf-8")

    assert list_gd_resources(tmp_path) == ["res://player.gd"]


def test_empty_project_still_emits_parseable_script(tmp_path: Path) -> None:
    source = build_sentinel_source(tmp_path)
    assert source.startswith("extends RefCounted\n")
    assert "func _init() -> void:" in source
    assert "preload(" not in source


def test_source_preloads_sorted_res_paths(tmp_path: Path) -> None:
    (tmp_path / "b.gd").write_text("extends Node\n", encoding="utf-8")
    (tmp_path / "a.gd").write_text("extends Node\n", encoding="utf-8")
    source = build_sentinel_source(tmp_path)
    assert 'const _p0 = preload("res://a.gd")' in source
    assert 'const _p1 = preload("res://b.gd")' in source
    assert source.index("res://a.gd") < source.index("res://b.gd")


def test_install_and_remove_are_idempotent(tmp_path: Path) -> None:
    (tmp_path / "player.gd").write_text("extends Node\n", encoding="utf-8")
    dest = install_sentinel(tmp_path)
    assert dest == sentinel_path(tmp_path)
    assert dest.is_file()
    assert SENTINEL_RES_PATH.endswith(SENTINEL_FILENAME)
    assert 'preload("res://player.gd")' in dest.read_text(encoding="utf-8")

    remove_sentinel(tmp_path)
    assert not dest.exists()
    remove_sentinel(tmp_path)
