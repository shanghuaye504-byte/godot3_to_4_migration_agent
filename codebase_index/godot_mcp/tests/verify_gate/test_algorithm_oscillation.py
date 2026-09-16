"""`algorithm.evaluate()` 的震荡检测测试 —— 方案文档 §4.2 第 3 条、§8 的 G-OSC。

覆盖要点：
- G-OSC：签名集合出现 S0→S1→S0（长度恰为 3 的 A→B→A）→
  `decision="OSCILLATION_ESCALATE"`，`hard_stop=True`。
- 反例：S0→S1→S2（三轮两两不同，没有回到 S0）→ 不触发震荡，落到无进展/正常分支。
- 反例：S0→S0→S0（三轮完全相同）→ 不触发震荡（`h[-1] == h[-2]` 时震荡条件本身就是
  False），应落到 `NO_PROGRESS_WARN`，两种检测不能互相误报。
- 语义限制回归（对应 `verifier_retry_gate_scheme.md` §4.1 的补齐说明）：把
  `oscillation_window` 配置改成 5，用一个 S0→S1→S2→S0 的 4 轮周期震荡样例，断言
  **不会**被当前算法识别为震荡——这是文档里明确写的"当前实现限制"，不是缺陷，
  测试要把这条限制锁住，避免后续有人"修好"了却没同步更新文档。
"""

from __future__ import annotations

from godot_mcp.verify_gate.algorithm import evaluate
from godot_mcp.verify_gate.config import RetryGateConfig

from tests.verify_gate.helpers import make_request, make_state, make_view


def test_aba_oscillation_escalates() -> None:
    state = make_state()
    cfg = RetryGateConfig()
    views = [make_view("s0"), make_view("s1"), make_view("s0")]
    results = [
        evaluate(state, make_request(views[i]), cfg) for i in range(3)
    ]
    assert results[0].decision == "CONTINUE"
    assert results[1].decision == "CONTINUE"
    assert results[2].decision == "OSCILLATION_ESCALATE"
    assert results[2].hard_stop is True
    assert results[2].directive is None


def test_three_distinct_signatures_are_not_oscillation() -> None:
    state = make_state()
    cfg = RetryGateConfig()
    views = [make_view("s0"), make_view("s1"), make_view("s2")]
    results = [
        evaluate(state, make_request(views[i]), cfg) for i in range(3)
    ]
    assert [r.decision for r in results] == ["CONTINUE", "CONTINUE", "CONTINUE"]
    assert all(r.hard_stop is False for r in results)


def test_three_identical_is_no_progress_not_oscillation() -> None:
    state = make_state()
    cfg = RetryGateConfig()
    view = make_view("s0")
    results = [
        evaluate(state, make_request(view), cfg) for i in (1, 2, 3)
    ]
    assert results[2].decision == "NO_PROGRESS_WARN"
    assert results[2].hard_stop is False
    assert results[2].directive


def test_four_cycle_not_detected_even_if_window_is_five() -> None:
    state = make_state()
    cfg = RetryGateConfig(oscillation_window=5)
    views = [make_view("s0"), make_view("s1"), make_view("s2"), make_view("s0")]
    results = [
        evaluate(state, make_request(views[i]), cfg) for i in range(4)
    ]
    assert all(r.decision != "OSCILLATION_ESCALATE" for r in results)
    assert results[-1].decision == "CONTINUE"
    assert results[-1].hard_stop is False
