"""`run_verify_tool` 胶水层测试：mock `run_verify`，不拉真实 Godot。

覆盖要点：
- 一次真实报错日志 → VerifyGateResult 形状正确、decision=CONTINUE
- 连续 3 次 TIMEOUT → CIRCUIT_OPEN
- 连续 3 轮相同日志 → NO_PROGRESS_WARN
- check_workspace 在 COLD 下先 V3，再 V1↔V2，并再 V1 一次
- check_file 缺 target → ValueError
"""

from __future__ import annotations

from pathlib import Path

from godot_mcp.config import Config
from godot_mcp.verify.runner import VerifyResult
from godot_mcp.verify_gate.config import RetryGateConfig
from godot_mcp.verify_gate.state_store import InMemoryStateStore
from godot_mcp.verify_gate.tool import gate_result_to_dict, run_verify_tool
from godot_mcp.verify_shell.cache import CLASS_CACHE_REL

_FIXTURES = Path(__file__).parent / "verify_filter" / "fixtures" / "godot_4_7_1"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _config(tmp_path: Path) -> Config:
    return Config(project_root=tmp_path, godot_binary="godot4")


def _warm(tmp_path: Path) -> None:
    dest = tmp_path / CLASS_CACHE_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("list=[]\n", encoding="utf-8")


def _ok(kind: str, stderr: str, stdout: str = "") -> VerifyResult:
    return VerifyResult(kind=kind, timed_out=False, exit_code=0, stdout=stdout, stderr=stderr)


def test_check_file_real_syntax_error_shape(tmp_path: Path) -> None:
    stderr = _load("sample_e_real_syntax_error.log")
    _warm(tmp_path)

    def spawn(kind: str, target: str | None, *_args: object) -> VerifyResult:
        assert kind == "V2"
        assert target == "res://orphan_bad_parse.gd"
        return _ok(kind, stderr)

    result = run_verify_tool(
        "check_file",
        "res://orphan_bad_parse.gd",
        session_id="s1",
        config=_config(tmp_path),
        gate_cfg=RetryGateConfig(),
        state_store=InMemoryStateStore(),
        run_verify_fn=spawn,
    )
    assert result.project_status == "HAS_ERRORS"
    assert result.decision == "CONTINUE"
    assert result.hard_stop is False
    assert result.round_index == 1
    assert result.root_cause_errors
    assert result.root_cause_errors[0].res_path == "res://orphan_bad_parse.gd"
    payload = gate_result_to_dict(result)
    assert payload["project_status"] == "HAS_ERRORS"
    assert payload["hard_stop"] is False
    assert isinstance(payload["signature_set"], list)
    assert payload["gdscript_complete"] is False
    assert payload["probe_incomplete"] is False
    assert "shader_checked" in payload


def test_three_timeouts_open_circuit(tmp_path: Path) -> None:
    store = InMemoryStateStore()
    cfg = _config(tmp_path)

    def spawn(*_args: object) -> VerifyResult:
        return VerifyResult(kind="V1", timed_out=True, exit_code=None, stdout="", stderr="")

    results = [
        run_verify_tool(
            "check_workspace",
            session_id="timeouts",
            config=cfg,
            gate_cfg=RetryGateConfig(),
            state_store=store,
            run_verify_fn=spawn,
        )
        for _ in range(3)
    ]
    assert [r.decision for r in results[:2]] == ["CONTINUE", "CONTINUE"]
    assert results[2].decision == "CIRCUIT_OPEN"
    assert results[2].hard_stop is True
    assert results[2].project_status == "INFRA_FAILURE"


def test_three_identical_rounds_warn_no_progress(tmp_path: Path) -> None:
    stderr = _load("sample_e_real_syntax_error.log")
    store = InMemoryStateStore()
    cfg = _config(tmp_path)

    def spawn(*_args: object) -> VerifyResult:
        return _ok("V2", stderr)

    results = [
        run_verify_tool(
            "check_file",
            "res://orphan_bad_parse.gd",
            session_id="stuck",
            config=cfg,
            gate_cfg=RetryGateConfig(),
            state_store=store,
            run_verify_fn=spawn,
        )
        for _ in range(3)
    ]
    assert results[0].decision == "CONTINUE"
    assert results[1].decision == "CONTINUE"
    assert results[2].decision == "NO_PROGRESS_WARN"
    assert results[2].hard_stop is False
    assert results[2].directive


def test_workspace_drills_down_pointers(tmp_path: Path) -> None:
    pointer_log = _load("sample_f_pointer_dep1.log")
    root_log = _load("sample_e_real_syntax_error.log")
    kinds: list[str] = []

    def spawn(kind: str, target: str | None, *_args: object) -> VerifyResult:
        kinds.append(kind)
        if kind == "V3":
            return _ok(kind, "")
        if kind == "V1":
            return _ok(kind, pointer_log)
        assert kind == "V2"
        assert target == "res://root_bad.gd"
        return _ok(kind, root_log)

    result = run_verify_tool(
        "check_workspace",
        session_id="merge",
        config=_config(tmp_path),
        gate_cfg=RetryGateConfig(),
        state_store=InMemoryStateStore(),
        run_verify_fn=spawn,
    )
    assert kinds == ["V3", "V1", "V2", "V1"]
    assert result.project_status == "HAS_ERRORS"
    assert result.pointers == []
    assert any(e.res_path == "res://orphan_bad_parse.gd" for e in result.root_cause_errors)


def test_workspace_rejects_csproj(tmp_path: Path) -> None:
    (tmp_path / "Game.csproj").write_text("<Project/>\n", encoding="utf-8")

    def spawn(*_args: object) -> VerifyResult:
        raise AssertionError("拒收后不应起进程")

    try:
        run_verify_tool(
            "check_workspace",
            config=_config(tmp_path),
            run_verify_fn=spawn,
        )
    except ValueError as exc:
        assert "GDExtension" in str(exc) or "C#" in str(exc)
    else:
        raise AssertionError("C# 项目应该被拒收")


def test_check_file_requires_target(tmp_path: Path) -> None:
    def spawn(*_args: object) -> VerifyResult:
        raise AssertionError("不应该起进程")

    try:
        run_verify_tool(
            "check_file",
            None,
            config=_config(tmp_path),
            run_verify_fn=spawn,
        )
    except ValueError as exc:
        assert "target" in str(exc)
    else:
        raise AssertionError("缺 target 应该抛 ValueError")


# --- CP5：内部组装 phase / diff，check_file COLD 预热 ---

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


def test_cp5_first_round_intake_wipes_uid_and_starts_v3(tmp_path: Path) -> None:
    store = InMemoryStateStore()
    (tmp_path / "a.gd").write_text("class_name Foo\n", encoding="utf-8")
    uid = tmp_path / "main.tscn.uid"
    uid.write_text("uid://abc\n", encoding="utf-8")
    kinds: list[str] = []

    def spawn(kind: str, *_args: object) -> VerifyResult:
        kinds.append(kind)
        if kind == "V3":
            _warm(tmp_path)
        return _ok(kind, "")

    run_verify_tool(
        "check_workspace",
        session_id="cp5",
        config=_config(tmp_path),
        gate_cfg=RetryGateConfig(),
        state_store=store,
        run_verify_fn=spawn,
    )
    assert kinds[0] == "V3"
    assert not uid.exists()


def test_cp5_second_round_class_name_triggers_v3_without_agent_diff(tmp_path: Path) -> None:
    store = InMemoryStateStore()
    (tmp_path / "a.gd").write_text("class_name Foo\n", encoding="utf-8")
    kinds: list[str] = []

    def spawn(kind: str, *_args: object) -> VerifyResult:
        kinds.append(kind)
        if kind == "V3":
            _warm(tmp_path)
        return _ok(kind, "")

    run_verify_tool(
        "check_workspace",
        session_id="cp5-cn",
        config=_config(tmp_path),
        gate_cfg=RetryGateConfig(),
        state_store=store,
        run_verify_fn=spawn,
    )
    kinds.clear()
    (tmp_path / "a.gd").write_text("class_name Bar\n", encoding="utf-8")
    run_verify_tool(
        "check_workspace",
        session_id="cp5-cn",
        config=_config(tmp_path),
        gate_cfg=RetryGateConfig(),
        state_store=store,
        run_verify_fn=spawn,
    )
    assert kinds[0] == "V3"


def test_cp5_second_round_ordinary_body_starts_with_v1(tmp_path: Path) -> None:
    store = InMemoryStateStore()
    (tmp_path / "a.gd").write_text("func f():\n\tx\n", encoding="utf-8")
    kinds: list[str] = []
    err = _load("sample_e_real_syntax_error.log")

    def spawn(kind: str, *_args: object) -> VerifyResult:
        kinds.append(kind)
        if kind == "V3":
            _warm(tmp_path)
            return _ok(kind, "")
        return _ok(kind, err)

    run_verify_tool(
        "check_workspace",
        session_id="cp5-body",
        config=_config(tmp_path),
        gate_cfg=RetryGateConfig(),
        state_store=store,
        run_verify_fn=spawn,
    )
    kinds.clear()
    (tmp_path / "a.gd").write_text("func f():\n\ty\n", encoding="utf-8")
    run_verify_tool(
        "check_workspace",
        session_id="cp5-body",
        config=_config(tmp_path),
        gate_cfg=RetryGateConfig(),
        state_store=store,
        run_verify_fn=spawn,
    )
    assert kinds[0] == "V1"


def test_cp5_explicit_empty_diff_skips_false_new_file_trigger(tmp_path: Path) -> None:
    _warm(tmp_path)
    (tmp_path / "a.gd").write_text("extends Node\n", encoding="utf-8")
    kinds: list[str] = []

    def spawn(kind: str, *_args: object) -> VerifyResult:
        kinds.append(kind)
        return _ok(kind, "")

    run_verify_tool(
        "check_workspace",
        session_id="cp5-override",
        config=_config(tmp_path),
        gate_cfg=RetryGateConfig(),
        state_store=InMemoryStateStore(),
        run_verify_fn=spawn,
        phase="iteration",
        unified_diff="",
    )
    assert kinds == ["V1", "V3"]


def test_cp5_check_file_cold_runs_v3_then_v2(tmp_path: Path) -> None:
    stderr = _load("sample_e_real_syntax_error.log")
    kinds: list[str] = []

    def spawn(kind: str, *_args: object) -> VerifyResult:
        kinds.append(kind)
        if kind == "V3":
            _warm(tmp_path)
            return _ok(kind, "")
        return _ok(kind, stderr)

    run_verify_tool(
        "check_file",
        "res://orphan_bad_parse.gd",
        session_id="cp5-file",
        config=_config(tmp_path),
        gate_cfg=RetryGateConfig(),
        state_store=InMemoryStateStore(),
        run_verify_fn=spawn,
    )
    assert kinds == ["V3", "V2"]


def test_cp5_check_file_cold_v3_timeout_skips_v2(tmp_path: Path) -> None:
    kinds: list[str] = []

    def spawn(kind: str, *_args: object) -> VerifyResult:
        kinds.append(kind)
        return VerifyResult(kind=kind, timed_out=True, exit_code=None, stdout="", stderr="")

    result = run_verify_tool(
        "check_file",
        "res://orphan_bad_parse.gd",
        session_id="cp5-file-to",
        config=_config(tmp_path),
        gate_cfg=RetryGateConfig(),
        state_store=InMemoryStateStore(),
        run_verify_fn=spawn,
    )
    assert kinds == ["V3"]
    assert result.project_status == "INFRA_FAILURE"


def test_cp5_check_file_warm_is_v2_only(tmp_path: Path) -> None:
    _warm(tmp_path)
    kinds: list[str] = []

    def spawn(kind: str, *_args: object) -> VerifyResult:
        kinds.append(kind)
        return _ok(kind, _load("sample_e_real_syntax_error.log"))

    run_verify_tool(
        "check_file",
        "res://orphan_bad_parse.gd",
        session_id="cp5-file-warm",
        config=_config(tmp_path),
        gate_cfg=RetryGateConfig(),
        state_store=InMemoryStateStore(),
        run_verify_fn=spawn,
    )
    assert kinds == ["V2"]


def test_cp5_probe_incomplete_leaks_from_tool(tmp_path: Path) -> None:
    kinds: list[str] = []

    def spawn(kind: str, *_args: object) -> VerifyResult:
        kinds.append(kind)
        if kind == "V3":
            return _ok(kind, "")
        if kind == "V1":
            return _ok(kind, _TWO_POINTERS)
        return _ok(kind, _load("sample_e_real_syntax_error.log"))

    result = run_verify_tool(
        "check_workspace",
        session_id="cp5-probe",
        config=_config(tmp_path),
        gate_cfg=RetryGateConfig(),
        state_store=InMemoryStateStore(),
        run_verify_fn=spawn,
        max_v2_targets=1,
    )
    payload = gate_result_to_dict(result)
    assert payload["probe_incomplete"] is True
    assert payload["gdscript_complete"] is False
    assert result.pointers
    assert "pointer_budget_exhausted" in result.caveats
