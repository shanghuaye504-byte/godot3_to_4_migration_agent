"""CP1：snapshot 生成的 git 风 diff 能喂给现有触发表。"""

from __future__ import annotations

from pathlib import Path

from godot_mcp.verify_shell.cache import CLASS_CACHE_REL
from godot_mcp.verify_shell.diff import parse_unified_diff
from godot_mcp.verify_shell.snapshot import diff_snapshots, scan_workspace
from godot_mcp.verify_shell.trigger import should_run_v3


def _warm(tmp_path: Path) -> None:
    dest = tmp_path / CLASS_CACHE_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("list=[]\n", encoding="utf-8")


def test_new_gd_triggers_iteration_v3(tmp_path: Path) -> None:
    (tmp_path / "a.gd").write_text("extends Node\n", encoding="utf-8")
    text = diff_snapshots({}, scan_workspace(tmp_path))
    assert "new file mode" in text
    view = parse_unified_diff(text)
    assert view.added_gd_file() is True
    _warm(tmp_path)
    assert should_run_v3(tmp_path, view, None, phase="iteration", v3_ran=False)


def test_class_name_rename_triggers(tmp_path: Path) -> None:
    old = {"a.gd": "class_name Foo\n"}
    (tmp_path / "a.gd").write_text("class_name Bar\n", encoding="utf-8")
    view = parse_unified_diff(diff_snapshots(old, scan_workspace(tmp_path)))
    assert any(line.startswith("+class_name ") or line.startswith("-class_name ") for line in view.plus_minus_lines)
    _warm(tmp_path)
    assert should_run_v3(tmp_path, view, None, phase="iteration", v3_ran=False)


def test_ordinary_body_skips_v3(tmp_path: Path) -> None:
    old = {"a.gd": "func f():\n\tx\n"}
    (tmp_path / "a.gd").write_text("func f():\n\ty\n", encoding="utf-8")
    view = parse_unified_diff(diff_snapshots(old, scan_workspace(tmp_path)))
    _warm(tmp_path)
    assert should_run_v3(tmp_path, view, None, phase="iteration", v3_ran=False) is False


def test_deleted_uid_triggers(tmp_path: Path) -> None:
    old = {"foo.uid": "uid://abc\n"}
    view = parse_unified_diff(diff_snapshots(old, scan_workspace(tmp_path)))
    assert view.deleted_uid() is True
    _warm(tmp_path)
    assert should_run_v3(tmp_path, view, None, phase="iteration", v3_ran=False)


def test_skips_godot_and_git_dirs(tmp_path: Path) -> None:
    (tmp_path / "a.gd").write_text("extends Node\n", encoding="utf-8")
    imported = tmp_path / ".godot" / "imported"
    imported.mkdir(parents=True)
    (imported / "x.uid").write_text("uid://hidden\n", encoding="utf-8")
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "x.gd").write_text("class_name Hidden\n", encoding="utf-8")
    snapshot = scan_workspace(tmp_path)
    assert list(snapshot) == ["a.gd"]


def test_empty_snapshot_treats_existing_gd_as_added(tmp_path: Path) -> None:
    (tmp_path / "a.gd").write_text("extends Node\n", encoding="utf-8")
    view = parse_unified_diff(diff_snapshots({}, scan_workspace(tmp_path)))
    assert view.added_gd_file() is True
