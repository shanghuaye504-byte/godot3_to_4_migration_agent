"""`algorithm.evaluate()` 的预算熔断测试 —— 方案文档 §4.2 第 2 条、§8 的
G-BUDGET / G-BUDGET-COST / G-PRIORITY。

覆盖要点：
- G-BUDGET：`rounds_used == rounds_limit` → `decision="BUDGET_EXCEEDED"`，`hard_stop=True`。
- G-BUDGET-COST（补齐的关键回归测试，对应任务 1 第 3 条修复）：多轮 `round_cost_usd`
  累计达到 `cost_limit_usd`，但 `rounds_used` 远未到 `rounds_limit` → 仍然
  `decision="BUDGET_EXCEEDED"`——验证 `round_cost_usd` 确实被累加进
  `state.cost_used_usd`，这个字段不再是恒为 0 的死字段。
- G-PRIORITY：同一次调用同时满足"无进展"（连续 N 轮签名不变）与"预算耗尽" → 只返回
  `BUDGET_EXCEEDED`，验证 §4.2 的优先级顺序（硬停止必须排在软提示之前判断）。
- 边界值：`rounds_used`/`cost_used_usd` 恰好等于（不是超过）阈值时也应触发，
  判定用 `>=` 不是 `>`。
"""

from __future__ import annotations

from godot_mcp.verify_gate.algorithm import evaluate
from godot_mcp.verify_gate.config import RetryGateConfig

from tests.verify_gate.helpers import make_request, make_state, make_view


def test_rounds_limit_exact_boundary() -> None:
    state = make_state()
    cfg = RetryGateConfig(rounds_limit=3)
    views = [make_view("s1"), make_view("s2"), make_view("s3")]
    results = [
        evaluate(state, make_request(views[i], round_index=i + 1), cfg)
        for i in range(3)
    ]
    assert [r.decision for r in results[:2]] == ["CONTINUE", "CONTINUE"]
    assert results[2].decision == "BUDGET_EXCEEDED"
    assert results[2].hard_stop is True
    assert results[2].directive is None
    assert state.rounds_used == 3
    assert results[2].remaining_budget.rounds_used == 3
    assert results[2].remaining_budget.rounds_limit == 3


def test_cost_limit_without_hitting_rounds() -> None:
    state = make_state()
    cfg = RetryGateConfig(cost_limit_usd=1.0, rounds_limit=40)
    view = make_view("sig-a")
    first = evaluate(
        state, make_request(view, round_index=1, round_cost_usd=0.4), cfg
    )
    second = evaluate(
        state, make_request(view, round_index=2, round_cost_usd=0.6), cfg
    )
    assert first.decision == "CONTINUE"
    assert first.hard_stop is False
    assert state.cost_used_usd == 1.0
    assert second.decision == "BUDGET_EXCEEDED"
    assert second.hard_stop is True
    assert second.remaining_budget.cost_used_usd == 1.0
    assert state.rounds_used == 2


def test_budget_outranks_no_progress() -> None:
    state = make_state()
    cfg = RetryGateConfig(rounds_limit=3, no_progress_window=3)
    view = make_view("stuck")
    results = [
        evaluate(state, make_request(view, round_index=i), cfg) for i in (1, 2, 3)
    ]
    assert results[2].decision == "BUDGET_EXCEEDED"
    assert results[2].hard_stop is True
