"""采集循环：mock spawn，不拉真实 Godot。"""

from __future__ import annotations

from pathlib import Path

from godot_mcp.verify.runner import VerifyResult
from godot_mcp.verify_shell.cache import CLASS_CACHE_REL
from godot_mcp.verify_shell.collect import MAX_V1_ROUNDS, MAX_V2_TARGETS, collect_workspace_view

_FIXTURES = Path(__file__).resolve().parents[1] / "verify_filter" / "fixtures" / "godot_4_7_1"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _ok(kind: str, stderr: str = "", stdout: str = "") -> VerifyResult:
    return VerifyResult(kind=kind, timed_out=False, exit_code=0, stdout=stdout, stderr=stderr)


def _warm(tmp_path: Path) -> None:
    dest = tmp_path / CLASS_CACHE_REL
    dest.parent.mkdir(parents=True)
    dest.write_text("list=[]\n", encoding="utf-8")


def test_default_pointer_budgets_are_provisional() -> None:
    assert MAX_V1_ROUNDS == 3
    assert MAX_V2_TARGETS == 50


def test_cold_runs_v3_then_v1_v2_then_repeat_v1(tmp_path: Path) -> None:
    pointer_log = _load("sample_f_pointer_dep1.log")
    root_log = _load("sample_e_real_syntax_error.log")
    kinds: list[str] = []

    def spawn(kind: str, target: str | None, *_args: object) -> VerifyResult:
        kinds.append(kind)
        if kind == "V3":
            return _ok("V3")
        if kind == "V1":
            return _ok("V1", pointer_log)
        assert target == "res://root_bad.gd"
        return _ok("V2", root_log)

    result = collect_workspace_view(
        project_root=tmp_path,
        godot_binary="godot4",
        spawn=spawn,
        timeout_s=10,
        phase="iteration",
    )
    assert kinds == ["V3", "V1", "V2", "V1"]
    assert result.infra_status == "OK"
    assert result.v3_ran is True
    assert result.v1_rounds == 2
    assert result.project_view.status == "HAS_ERRORS"


def test_warm_clean_v1_then_final_gate_v3(tmp_path: Path) -> None:
    _warm(tmp_path)
    kinds: list[str] = []

    def spawn(kind: str, *_args: object) -> VerifyResult:
        kinds.append(kind)
        return _ok(kind)

    result = collect_workspace_view(
        project_root=tmp_path,
        godot_binary="godot4",
        spawn=spawn,
        timeout_s=10,
        phase="iteration",
    )
    assert kinds == ["V1", "V3"]
    assert result.project_view.gdscript_complete is True
    assert result.project_view.shader_checked is True
    assert result.v3_ran is True


def test_v3_timeout_is_infra_before_v1(tmp_path: Path) -> None:
    def spawn(kind: str, *_args: object) -> VerifyResult:
        assert kind == "V3"
        return VerifyResult(kind="V3", timed_out=True, exit_code=None, stdout="", stderr="")

    result = collect_workspace_view(
        project_root=tmp_path,
        godot_binary="godot4",
        spawn=spawn,
        timeout_s=10,
        phase="iteration",
    )
    assert result.infra_status == "TIMEOUT"
    assert result.v1_rounds == 0


_TWO_POINTERS = """\
SCRIPT ERROR: Parse Error: Could not preload resource script "res://root_bad.gd".
          at: GDScript::reload (res://dep_1.gd:3)
SCRIPT ERROR: Parse Error: Could not resolve script "res://root_bad.gd".
          at: GDScript::reload (res://dep_1.gd:3)
SCRIPT ERROR: Parse Error: Could not preload resource script "res://other_bad.gd".
          at: GDScript::reload (res://dep_2.gd:3)
SCRIPT ERROR: Parse Error: Could not resolve script "res://other_bad.gd".
          at: GDScript::reload (res://dep_2.gd:3)
"""


def test_v2_budget_leaves_pending_and_caveat(tmp_path: Path) -> None:
    root_log = _load("sample_e_real_syntax_error.log")
    v2_targets: list[str] = []

    def spawn(kind: str, target: str | None, *_args: object) -> VerifyResult:
        if kind == "V3":
            return _ok("V3")
        if kind == "V1":
            return _ok("V1", _TWO_POINTERS)
        v2_targets.append(target or "")
        return _ok("V2", root_log)

    result = collect_workspace_view(
        project_root=tmp_path,
        godot_binary="godot4",
        spawn=spawn,
        timeout_s=10,
        phase="iteration",
        max_v2_targets=1,
    )
    assert len(v2_targets) == 1
    assert result.project_view.pending_pointers
    assert "pointer_budget_exhausted" in result.project_view.caveats
    assert result.project_view.gdscript_complete is False


def test_v2_timeout_leaves_pending_without_infra(tmp_path: Path) -> None:
    def spawn(kind: str, target: str | None, *_args: object) -> VerifyResult:
        if kind == "V3":
            return _ok("V3")
        if kind == "V1":
            return _ok("V1", _load("sample_f_pointer_dep1.log"))
        return VerifyResult(kind="V2", timed_out=True, exit_code=None, stdout="", stderr="")

    result = collect_workspace_view(
        project_root=tmp_path,
        godot_binary="godot4",
        spawn=spawn,
        timeout_s=10,
        phase="iteration",
    )
    assert result.infra_status == "OK"
    assert result.project_view.pending_pointers
    assert "pointer_probe_incomplete" in result.project_view.caveats
    assert "pointer_budget_exhausted" not in result.project_view.caveats
