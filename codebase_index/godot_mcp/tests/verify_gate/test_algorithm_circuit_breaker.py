"""`algorithm.evaluate()` 的基础设施熔断与 `project_status` 合成测试 —— 方案文档
§4.2 第 1 条、§8 的 G-INFRA / G-INFRA-STATUS。

覆盖要点：
- G-INFRA：连续 `infra_failure_streak_limit`（默认 3）次 `infra_status != "OK"` →
  `decision="CIRCUIT_OPEN"`，`hard_stop=True`，`state.circuit_state` 变为 `"OPEN"`。
- G-INFRA-STATUS（补齐的关键回归测试，对应任务 1 第 5 条修复）：单次
  `infra_status="TIMEOUT"`，尚未达到 `infra_failure_streak_limit` → `decision="CONTINUE"`
  （未硬停止），**但** `VerifyGateResult.project_status == "INFRA_FAILURE"`——不能因为
  没到熔断阈值就沿用 `request.project_view.status`，那份数据在超时/崩溃时可能残缺或陈旧。
- 中途恢复：`infra_status` 从连续几次 `!= "OK"` 变回 `"OK"` → `infra_failure_streak`
  清零，不会累积到跨"恢复"的下一次异常里。
"""

from __future__ import annotations

from godot_mcp.verify_gate.algorithm import evaluate
from godot_mcp.verify_gate.config import RetryGateConfig

from tests.verify_gate.helpers import make_request, make_state, make_view


def test_single_timeout_is_infra_failure_but_continues() -> None:
    state = make_state()
    view = make_view("sig-a")
    result = evaluate(
        state,
        make_request(view, infra_status="TIMEOUT"),
        RetryGateConfig(),
    )
    assert result.decision == "CONTINUE"
    assert result.hard_stop is False
    assert result.project_status == "INFRA_FAILURE"
    assert state.infra_failure_streak == 1
    assert state.circuit_state == "CLOSED"


def test_three_consecutive_infra_failures_open_circuit() -> None:
    state = make_state()
    cfg = RetryGateConfig()
    view = make_view()
    statuses = ("TIMEOUT", "CRASH", "TIMEOUT")
    results = []
    for i, status in enumerate(statuses, start=1):
        results.append(
            evaluate(state, make_request(view, infra_status=status), cfg)
        )

    assert [r.decision for r in results[:2]] == ["CONTINUE", "CONTINUE"]
    assert results[2].decision == "CIRCUIT_OPEN"
    assert results[2].hard_stop is True
    assert results[2].project_status == "INFRA_FAILURE"
    assert results[2].directive is None
    assert state.circuit_state == "OPEN"
    assert state.infra_failure_streak == 3


def test_infra_recovery_resets_streak() -> None:
    state = make_state()
    # 拉开无进展窗口，避免本测试只关心 streak 时被 NO_PROGRESS 抢走判定
    cfg = RetryGateConfig(no_progress_window=10)
    view = make_view("sig-a")
    evaluate(state, make_request(view, infra_status="TIMEOUT"), cfg)
    evaluate(state, make_request(view, infra_status="CRASH"), cfg)
    assert state.infra_failure_streak == 2

    recovered = evaluate(
        state, make_request(view, infra_status="OK"), cfg
    )
    assert recovered.decision == "CONTINUE"
    assert recovered.project_status == "HAS_ERRORS"
    assert state.infra_failure_streak == 0
    assert state.circuit_state == "CLOSED"

    evaluate(state, make_request(view, infra_status="TIMEOUT"), cfg)
    assert state.infra_failure_streak == 1
    assert state.circuit_state == "CLOSED"
