"""`should_run_v3` 三个 phase 互不串味。"""

from __future__ import annotations

from pathlib import Path

from godot_mcp.verify_shell.cache import CLASS_CACHE_REL
from godot_mcp.verify_shell.diff import parse_unified_diff
from godot_mcp.verify_shell.trigger import should_run_v3


def _warm(tmp_path: Path) -> None:
    dest = tmp_path / CLASS_CACHE_REL
    dest.parent.mkdir(parents=True)
    dest.write_text("list=[]\n", encoding="utf-8")


def test_intake_cold_always_v3(tmp_path: Path) -> None:
    assert should_run_v3(tmp_path, parse_unified_diff(""), None, phase="intake", v3_ran=False)


def test_intake_warm_without_wipe_skips(tmp_path: Path) -> None:
    _warm(tmp_path)
    assert (
        should_run_v3(
            tmp_path,
            parse_unified_diff(""),
            None,
            phase="intake",
            v3_ran=False,
            intake_needs_uid_wipe=False,
        )
        is False
    )


def test_intake_warm_after_wipe_runs(tmp_path: Path) -> None:
    _warm(tmp_path)
    assert should_run_v3(
        tmp_path,
        parse_unified_diff(""),
        None,
        phase="intake",
        v3_ran=False,
        intake_needs_uid_wipe=True,
    )


def test_iteration_cold_runs_even_empty_diff(tmp_path: Path) -> None:
    assert should_run_v3(tmp_path, parse_unified_diff(""), None, phase="iteration", v3_ran=False)


def test_iteration_warm_ordinary_body_skips(tmp_path: Path) -> None:
    _warm(tmp_path)
    diff = parse_unified_diff(
        "diff --git a/a.gd b/a.gd\n--- a/a.gd\n+++ b/a.gd\n@@ -1 +1 @@\n-x\n+y\n"
    )
    assert should_run_v3(tmp_path, diff, None, phase="iteration", v3_ran=False) is False


def test_iteration_class_name_triggers(tmp_path: Path) -> None:
    _warm(tmp_path)
    diff = parse_unified_diff(
        "diff --git a/a.gd b/a.gd\n--- a/a.gd\n+++ b/a.gd\n@@ -1 +1 @@\n-class_name Foo\n+class_name Bar\n"
    )
    assert should_run_v3(tmp_path, diff, None, phase="iteration", v3_ran=False)
