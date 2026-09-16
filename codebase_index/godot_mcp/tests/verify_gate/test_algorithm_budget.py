"""`algorithm.evaluate()` 的预算熔断测试。

覆盖要点：
- G-BUDGET：`rounds_used == rounds_limit` → `decision="BUDGET_EXCEEDED"`，`hard_stop=True`。
- G-PRIORITY：同一次调用同时满足"无进展"与"预算耗尽" → 只返回 `BUDGET_EXCEEDED`。
- 边界值：`rounds_used` 恰好等于阈值时也应触发，判定用 `>=` 不是 `>`。
成本 / token 不在 Gate 内熔断。
"""

from __future__ import annotations

from godot_mcp.verify_gate.algorithm import evaluate
from godot_mcp.verify_gate.config import RetryGateConfig

from tests.verify_gate.helpers import make_request, make_state, make_view


def test_rounds_limit_exact_boundary() -> None:
    state = make_state()
    cfg = RetryGateConfig(rounds_limit=3)
    views = [make_view("s1"), make_view("s2"), make_view("s3")]
    results = [evaluate(state, make_request(views[i]), cfg) for i in range(3)]
    assert [r.decision for r in results[:2]] == ["CONTINUE", "CONTINUE"]
    assert results[2].decision == "BUDGET_EXCEEDED"
    assert results[2].hard_stop is True
    assert results[2].directive is None
    assert state.rounds_used == 3
    assert results[2].remaining_budget.rounds_used == 3
    assert results[2].remaining_budget.rounds_limit == 3


def test_budget_outranks_no_progress() -> None:
    state = make_state()
    cfg = RetryGateConfig(rounds_limit=3, no_progress_window=3)
    view = make_view("stuck")
    results = [evaluate(state, make_request(view), cfg) for _ in range(3)]
    assert results[2].decision == "BUDGET_EXCEEDED"
    assert results[2].hard_stop is True
