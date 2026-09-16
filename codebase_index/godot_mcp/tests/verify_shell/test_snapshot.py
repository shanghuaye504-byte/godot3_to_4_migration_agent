"""CP1：snapshot 生成的 git 风 diff 能喂给现有触发表。

硬上限：文件数 / 字节超限立即拒收，且不先 read_text 超限文件。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from godot_mcp.verify_shell.cache import CLASS_CACHE_REL
from godot_mcp.verify_shell.diff import parse_unified_diff
from godot_mcp.verify_shell.snapshot import (
    MAX_SNAPSHOT_BYTES,
    MAX_SNAPSHOT_FILES,
    SnapshotTooLargeError,
    diff_snapshots,
    scan_workspace,
)
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


def test_snapshot_limit_constants() -> None:
    assert MAX_SNAPSHOT_FILES == 2000
    assert MAX_SNAPSHOT_BYTES == 1024 * 1024 * 1024


def test_at_file_limit_passes(tmp_path: Path) -> None:
    for i in range(3):
        (tmp_path / f"f{i}.gd").write_text("extends Node\n", encoding="utf-8")
    snapshot = scan_workspace(tmp_path, max_files=3, max_bytes=10_000)
    assert len(snapshot) == 3


def test_over_file_limit_is_rejected(tmp_path: Path) -> None:
    for i in range(4):
        (tmp_path / f"f{i}.gd").write_text("extends Node\n", encoding="utf-8")
    with pytest.raises(SnapshotTooLargeError, match="4 个") as exc_info:
        scan_workspace(tmp_path, max_files=3, max_bytes=10_000)
    message = str(exc_info.value)
    assert "上限为 3 个" in message
    assert "内存快照不承接该仓" in message


def test_at_byte_limit_passes(tmp_path: Path) -> None:
    payload = "x" * 100
    (tmp_path / "a.gd").write_text(payload, encoding="utf-8")
    snapshot = scan_workspace(tmp_path, max_files=10, max_bytes=100)
    assert snapshot["a.gd"] == payload


def test_over_byte_limit_rejects_before_read_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "huge.tres"
    target.write_bytes(b"x" * 200)
    read_paths: list[str] = []
    original = Path.read_text

    def tracking_read(self: Path, *args: object, **kwargs: object) -> str:
        read_paths.append(self.as_posix())
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", tracking_read)
    with pytest.raises(SnapshotTooLargeError, match="200 字节") as exc_info:
        scan_workspace(tmp_path, max_files=10, max_bytes=100)
    assert target.as_posix() not in read_paths
    message = str(exc_info.value)
    assert "上限为 10 个 / 100 字节" in message
    assert "内存快照不承接该仓" in message


def test_godot_and_git_dirs_do_not_count_toward_limit(tmp_path: Path) -> None:
    (tmp_path / "a.gd").write_text("extends Node\n", encoding="utf-8")
    godot_dir = tmp_path / ".godot" / "imported"
    godot_dir.mkdir(parents=True)
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    for i in range(5):
        (godot_dir / f"hidden{i}.uid").write_text("uid://h\n", encoding="utf-8")
        (git_dir / f"hidden{i}.gd").write_text("class_name Hidden\n", encoding="utf-8")
    snapshot = scan_workspace(tmp_path, max_files=1, max_bytes=10_000)
    assert list(snapshot) == ["a.gd"]


def test_non_snapshot_suffixes_do_not_count_toward_limit(tmp_path: Path) -> None:
    (tmp_path / "a.gd").write_text("extends Node\n", encoding="utf-8")
    (tmp_path / "scene.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    (tmp_path / "icon.png").write_bytes(b"\x89PNG")
    snapshot = scan_workspace(tmp_path, max_files=1, max_bytes=10_000)
    assert list(snapshot) == ["a.gd"]
