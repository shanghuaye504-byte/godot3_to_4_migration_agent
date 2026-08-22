"""Fake Godot 的预设脚本库（按 fixture / 指令别名存放预期输出）。

假二进制不得被任何“已确认”结论引用。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

_ENGINE_BANNER = "Godot Engine 4.7.1.stable.official.fake\n"

_CASCADE_STDERR = (
    'SCRIPT ERROR: Parse Error: Expected ":" after "void".\n'
    "   at: GDScript::reload (res://root_bad.gd:3)\n"
    'ERROR: Failed to load script "res://dep_1.gd" with error "Compilation failed".\n'
    'ERROR: Failed to load script "res://dep_2.gd" with error "Compilation failed".\n'
    'ERROR: Failed to compile depended scripts.\n'
)

_CLEAN_V5_STDOUT = _ENGINE_BANNER + "CLEAN_OK\n"
_CASCADE_V5_STDOUT = _ENGINE_BANNER + "NP_CASCADE_MAIN_OK\n"


def classify_fixture(project_path: Path) -> str:
    project_path = Path(project_path)
    if (project_path / "root_bad.gd").is_file():
        return "cascade"
    godot = project_path / "project.godot"
    if godot.is_file() and 'config/name="CleanControl"' in godot.read_text(encoding="utf-8"):
        return "clean"
    return "unknown"


def classify_command(argv: list) -> str:
    tokens = [str(t) for t in argv]
    joined = " ".join(tokens)
    if "--version" in tokens or "-v" in tokens:
        return "version"
    if "--quit-after" in tokens:
        return "V6"
    script = ""
    if "--script" in tokens:
        idx = tokens.index("--script")
        if idx + 1 < len(tokens):
            script = tokens[idx + 1]
    verbose = "--verbose" in tokens
    debug = "--debug" in tokens
    check_only = "--check-only" in tokens
    editor = "--editor" in tokens
    do_import = "--import" in tokens

    if "__probe_sentinel.gd" in script:
        if debug:
            return "V8_V1"
        if verbose:
            return "V7_V1"
        return "V1"
    if script and check_only:
        if debug:
            return "V8_V2"
        if verbose:
            return "V7_V2"
        return "V2"
    if editor and do_import:
        return "V7_V3" if verbose else "V3"
    if do_import:
        return "V4"
    if check_only:
        if debug:
            return "V8_V1"
        if verbose:
            return "V7_V1"
        return "V1"
    return "V5"


def _response(*, stdout: str = "", stderr: str = "", returncode: int = 0, sleep: float = 0.01) -> dict:
    return {
        "stdout": stdout,
        "stderr": stderr,
        "returncode": returncode,
        "sleep": sleep,
    }


def lookup(argv: list, *, cwd: Optional[Path] = None, project_path: Optional[Path] = None) -> dict:
    """按 argv + 工作区内容返回预设 stdout/stderr/rc。"""
    tokens = [str(t) for t in argv]
    command = classify_command(tokens)

    if command == "version":
        return _response(stdout="4.7.1.stable.official.fake\n", sleep=0.0)

    if project_path is None:
        if "--path" in tokens:
            idx = tokens.index("--path")
            if idx + 1 < len(tokens):
                project_path = Path(tokens[idx + 1])
        else:
            project_path = Path(cwd or ".")

    fixture = classify_fixture(Path(project_path))
    hang = command.startswith("V8") or "--debug" in tokens
    if hang:
        return _response(stdout=_ENGINE_BANNER, stderr="", returncode=0, sleep=3600.0)

    if fixture == "cascade" and command in {"V1", "V7_V1"}:
        return _response(stdout=_ENGINE_BANNER, stderr=_CASCADE_STDERR, returncode=1)

    if fixture == "cascade" and command in {"V3", "V4", "V7_V3"}:
        return _response(stdout=_ENGINE_BANNER, stderr=_CASCADE_STDERR, returncode=0)

    if command in {"V5", "V6"}:
        stdout = _CASCADE_V5_STDOUT if fixture == "cascade" else _CLEAN_V5_STDOUT
        return _response(stdout=stdout, returncode=0)

    return _response(stdout=_ENGINE_BANNER, returncode=0)
