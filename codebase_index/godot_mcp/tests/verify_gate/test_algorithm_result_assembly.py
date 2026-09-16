"""`_result()` 辅助函数的组装逻辑测试 —— G-DIFF / G-DIFF-FIRST-ROUND。

覆盖要点：
- G-DIFF：上一轮签名集合 `{A,B}`，本轮 `{B,C}` → `diff.new_signatures={C}`，
  `diff.resolved_signatures={A}`，`diff.persisted_signatures={B}`。
- G-DIFF-FIRST-ROUND：首轮调用，本轮签名集合 `{A,B}` → `diff.new_signatures={A,B}`，
  另外两个为空。
- `remaining_budget` 只反映轮次。
"""

from __future__ import annotations

from godot_mcp.verify_gate.algorithm import evaluate
from godot_mcp.verify_gate.config import RetryGateConfig

from tests.verify_gate.helpers import make_request, make_state, make_view


def test_first_round_diff_treats_all_as_new() -> None:
    state = make_state()
    cfg = RetryGateConfig()
    result = evaluate(state, make_request(make_view("A", "B")), cfg)
    assert result.diff.new_signatures == frozenset({"A", "B"})
    assert result.diff.resolved_signatures == frozenset()
    assert result.diff.persisted_signatures == frozenset()
    assert result.signature_set == frozenset({"A", "B"})
    assert result.round_index == 1
    assert result.remaining_budget.rounds_used == 1
    assert result.remaining_budget.rounds_limit == cfg.rounds_limit


def test_second_round_diff_splits_new_resolved_persisted() -> None:
    state = make_state()
    cfg = RetryGateConfig()
    evaluate(state, make_request(make_view("A", "B")), cfg)
    result = evaluate(state, make_request(make_view("B", "C")), cfg)
    assert result.diff.new_signatures == frozenset({"C"})
    assert result.diff.resolved_signatures == frozenset({"A"})
    assert result.diff.persisted_signatures == frozenset({"B"})


def test_passthrough_fields_come_from_project_view() -> None:
    state = make_state()
    view = make_view("A", pointers=("ptr",), status="HAS_ERRORS")
    view.caveats.append("shader_not_checked")
    result = evaluate(state, make_request(view), RetryGateConfig())
    assert result.project_status == "HAS_ERRORS"
    assert [e.local_signature for e in result.root_cause_errors] == ["A"]
    assert [e.local_signature for e in result.pointers] == ["ptr"]
    assert "shader_not_checked" in result.caveats
    assert result.untrusted_files == view.untrusted_files


def test_complete_view_sets_probe_flags_false() -> None:
    state = make_state()
    result = evaluate(state, make_request(make_view()), RetryGateConfig())
    assert result.gdscript_complete is True
    assert result.probe_incomplete is False
    assert result.decision == "CONTINUE"
    assert result.hard_stop is False


def test_pending_pointers_set_probe_incomplete_without_hard_stop() -> None:
    state = make_state()
    result = evaluate(
        state,
        make_request(make_view(pointers=("p1",))),
        RetryGateConfig(),
    )
    assert result.probe_incomplete is True
    assert result.gdscript_complete is False
    assert result.decision == "CONTINUE"
    assert result.hard_stop is False


def test_shader_checked_passthrough() -> None:
    state = make_state()
    view = make_view(shader_checked=True)
    result = evaluate(state, make_request(view), RetryGateConfig())
    assert result.shader_checked is True
