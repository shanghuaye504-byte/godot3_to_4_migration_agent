"""UID wipe：只删工作区 sidecar，不动 `.godot/`。"""

from __future__ import annotations

from pathlib import Path

from godot_mcp.verify_shell.uid import list_uid_sidecars, wipe_uid_sidecars


def test_wipes_project_uid_keeps_godot_cache(tmp_path: Path) -> None:
    scene = tmp_path / "main.tscn.uid"
    scene.write_text("uid://abc\n", encoding="utf-8")
    cache = tmp_path / ".godot" / "imported" / "x.uid"
    cache.parent.mkdir(parents=True)
    cache.write_text("uid://cache\n", encoding="utf-8")

    assert list_uid_sidecars(tmp_path) == [scene]
    removed = wipe_uid_sidecars(tmp_path)
    assert removed == [scene]
    assert not scene.exists()
    assert cache.exists()
