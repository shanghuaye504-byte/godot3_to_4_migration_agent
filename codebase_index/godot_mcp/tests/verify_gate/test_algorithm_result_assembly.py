"""`_result()` 辅助函数的组装逻辑测试 —— 方案文档 §8 的 G-DIFF / G-DIFF-FIRST-ROUND /
G-ROUND-DRIFT。这些断言横跨全部 `decision` 分支（`_result` 是所有分支共用的组装点），
单独成文件，不依赖某一个具体的判定条件。

覆盖要点：
- G-DIFF：上一轮签名集合 `{A,B}`，本轮 `{B,C}` → `diff.new_signatures={C}`，
  `diff.resolved_signatures={A}`，`diff.persisted_signatures={B}`。
- G-DIFF-FIRST-ROUND（补齐的关键回归测试，对应任务 1 第 7 条修复）：首轮调用
  （`len(state.signature_history) == 1`），本轮签名集合 `{A,B}` → `diff.new_signatures=
  {A,B}`，`diff.resolved_signatures=∅`，`diff.persisted_signatures=∅`——没有"上一轮"
  可比时不应该抛异常或返回错误的 diff。
- G-ROUND-DRIFT（补齐的关键回归测试，对应任务 1 第 8 条修复）：`request.round_index`
  与内部 `state.rounds_used + 1` 不一致时，不中断执行、`decision`/`hard_stop` 不受
  影响，但返回的 `reason` 字符串里必须包含偏差提示（验证 §4.3 步骤 0 的防御性校验
  只记录、不阻断，且确实"记录"了，不是承诺了却什么都没做）。
- `remaining_budget`（`BudgetSnapshot`）在每个分支里都正确反映
  `state.rounds_used`/`cfg.rounds_limit`/`state.cost_used_usd`/`cfg.cost_limit_usd`。
"""

from __future__ import annotations

from godot_mcp.verify_gate.algorithm import evaluate
from godot_mcp.verify_gate.config import RetryGateConfig

from tests.verify_gate.helpers import make_request, make_state, make_view


def test_first_round_diff_treats_all_as_new() -> None:
    state = make_state()
    cfg = RetryGateConfig()
    result = evaluate(state, make_request(make_view("A", "B"), round_index=1), cfg)
    assert result.diff.new_signatures == frozenset({"A", "B"})
    assert result.diff.resolved_signatures == frozenset()
    assert result.diff.persisted_signatures == frozenset()
    assert result.signature_set == frozenset({"A", "B"})
    assert result.round_index == 1
    assert result.remaining_budget.rounds_used == 1
    assert result.remaining_budget.rounds_limit == cfg.rounds_limit
    assert result.remaining_budget.cost_used_usd == 0.0
    assert result.remaining_budget.cost_limit_usd == cfg.cost_limit_usd


def test_second_round_diff_splits_new_resolved_persisted() -> None:
    state = make_state()
    cfg = RetryGateConfig()
    evaluate(state, make_request(make_view("A", "B"), round_index=1), cfg)
    result = evaluate(state, make_request(make_view("B", "C"), round_index=2), cfg)
    assert result.diff.new_signatures == frozenset({"C"})
    assert result.diff.resolved_signatures == frozenset({"A"})
    assert result.diff.persisted_signatures == frozenset({"B"})


def test_round_index_drift_is_recorded_not_fatal() -> None:
    state = make_state()
    cfg = RetryGateConfig()
    result = evaluate(
        state, make_request(make_view("A"), round_index=9), cfg
    )
    assert result.decision == "CONTINUE"
    assert result.hard_stop is False
    assert "调用方 round_index 与内部计数不一致" in result.reason
    assert result.round_index == 1


def test_passthrough_fields_come_from_project_view() -> None:
    state = make_state()
    view = make_view("A", pointers=("ptr",), status="HAS_ERRORS")
    view.caveats.append("shader_not_checked")
    result = evaluate(state, make_request(view, round_index=1), RetryGateConfig())
    assert result.project_status == "HAS_ERRORS"
    assert [e.local_signature for e in result.root_cause_errors] == ["A"]
    assert [e.local_signature for e in result.pointers] == ["ptr"]
    assert "shader_not_checked" in result.caveats
    assert result.untrusted_files == view.untrusted_files


def test_complete_view_sets_probe_flags_false() -> None:
    state = make_state()
    result = evaluate(state, make_request(make_view(), round_index=1), RetryGateConfig())
    assert result.gdscript_complete is True
    assert result.probe_incomplete is False
    assert result.decision == "CONTINUE"
    assert result.hard_stop is False


def test_pending_pointers_set_probe_incomplete_without_hard_stop() -> None:
    state = make_state()
    result = evaluate(
        state,
        make_request(make_view(pointers=("p1",)), round_index=1),
        RetryGateConfig(),
    )
    assert result.probe_incomplete is True
    assert result.gdscript_complete is False
    assert result.decision == "CONTINUE"
    assert result.hard_stop is False


def test_shader_checked_passthrough() -> None:
    state = make_state()
    view = make_view(shader_checked=True)
    result = evaluate(state, make_request(view, round_index=1), RetryGateConfig())
    assert result.shader_checked is True
