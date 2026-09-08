"""断言 VERIFY_COMMANDS 里的命令行参数没被意外改动（白名单回归保护）。

覆盖要点：
- kind 集合恰好是 {"V1", "V2", "V3"}，不多不少
- 每个条目的 argv 与探针锁定的常量逐元素一致（含 --quit）
- V1 固定指向 res://__probe_sentinel.gd，忽略 target
- V2 对绝对路径、相对路径、res:// 路径都能正确转成 res:// 形式
- 白名单不含 check_all.gd / --debug / --verbose
"""

from __future__ import annotations

from pathlib import Path

import pytest

from godot_mcp.verify.commands import SENTINEL_RES_PATH, VERIFY_COMMANDS


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path / "game"


def test_kind_set_is_exactly_v1_v2_v3() -> None:
    assert set(VERIFY_COMMANDS.keys()) == {"V1", "V2", "V3"}


def test_v1_argv_is_sentinel_check(project_root: Path) -> None:
    argv = VERIFY_COMMANDS["V1"]("anything", project_root)
    assert argv == [
        "--headless",
        "--path",
        str(project_root),
        "--check-only",
        "--script",
        SENTINEL_RES_PATH,
        "--quit",
    ]


def test_v1_ignores_none_target(project_root: Path) -> None:
    argv = VERIFY_COMMANDS["V1"](None, project_root)
    assert argv[argv.index("--script") + 1] == SENTINEL_RES_PATH
    assert "--quit" in argv


def test_v2_with_res_path(project_root: Path) -> None:
    argv = VERIFY_COMMANDS["V2"]("res://player.gd", project_root)
    assert argv == [
        "--headless",
        "--path",
        str(project_root),
        "--script",
        "res://player.gd",
        "--check-only",
        "--quit",
    ]


def test_v2_with_relative_path(project_root: Path) -> None:
    argv = VERIFY_COMMANDS["V2"]("scripts/player.gd", project_root)
    assert argv == [
        "--headless",
        "--path",
        str(project_root),
        "--script",
        "res://scripts/player.gd",
        "--check-only",
        "--quit",
    ]


def test_v2_with_absolute_path_inside_project(project_root: Path) -> None:
    abs_target = str(project_root / "scripts" / "player.gd")
    argv = VERIFY_COMMANDS["V2"](abs_target, project_root)
    assert argv == [
        "--headless",
        "--path",
        str(project_root),
        "--script",
        "res://scripts/player.gd",
        "--check-only",
        "--quit",
    ]


def test_v2_with_absolute_path_outside_project_raises(project_root: Path) -> None:
    with pytest.raises(ValueError):
        VERIFY_COMMANDS["V2"]("/tmp/outside.gd", project_root)


def test_v2_requires_target(project_root: Path) -> None:
    with pytest.raises(ValueError, match="V2"):
        VERIFY_COMMANDS["V2"](None, project_root)


def test_v3_import_argv(project_root: Path) -> None:
    argv = VERIFY_COMMANDS["V3"](None, project_root)
    assert argv == [
        "--headless",
        "--path",
        str(project_root),
        "--editor",
        "--import",
        "--quit",
    ]


def test_whitelist_excludes_rejected_probe_flags(project_root: Path) -> None:
    samples = [
        VERIFY_COMMANDS["V1"](None, project_root),
        VERIFY_COMMANDS["V2"]("res://player.gd", project_root),
        VERIFY_COMMANDS["V3"](None, project_root),
    ]
    joined = " ".join(token for argv in samples for token in argv)
    assert "check_all.gd" not in joined
    assert "--debug" not in joined
    assert "--verbose" not in joined
    assert "--quit-after" not in joined


def test_no_shell_metacharacters_in_v2_constant_parts(project_root: Path) -> None:
    argv = VERIFY_COMMANDS["V2"]("res://player.gd", project_root)
    assert argv == [
        "--headless",
        "--path",
        str(project_root),
        "--script",
        "res://player.gd",
        "--check-only",
        "--quit",
    ]
    for token in argv:
        if token in {str(project_root), "res://player.gd"}:
            continue
        assert not any(ch in token for ch in ";&|$`")
