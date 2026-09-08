"""`algorithm.evaluate()` 的无进展检测测试 —— 方案文档 §4.2 第 4 条、§8 的 G-NOPROG / G-PROGRESS。

覆盖要点：
- G-CONT：首轮，任意 `root_cause_errors` 集合 → `decision="CONTINUE"`，`hard_stop=False`。
- G-PROGRESS：连续 3 轮签名集合递减且互不相同 → `decision="CONTINUE"`（有进展，
  不应误触发无进展）。
- G-NOPROG：连续 `no_progress_window`（默认 3）轮签名集合完全相同 →
  `decision="NO_PROGRESS_WARN"`，`hard_stop=False`，`directive` 非空且给出具体、
  可执行的策略调整建议（不是空话"再试一次"）。
- G-SYMPTOM-EXCLUDED：本轮唯一变化是 `project_view.symptoms`/`pending_pointers`/
  `dropped` 里新增了一条，`root_cause_errors` 不变 → 签名集合不受影响，不触发任何
  状态变化（验证 `project_signature_set` 只投影 `root_cause_errors`）。
"""

from __future__ import annotations

from godot_mcp.verify_gate.algorithm import evaluate, project_signature_set
from godot_mcp.verify_gate.config import RetryGateConfig

from tests.verify_gate.helpers import make_request, make_state, make_view


def test_first_round_continues() -> None:
    state = make_state()
    result = evaluate(
        state, make_request(make_view("err"), round_index=1), RetryGateConfig()
    )
    assert result.decision == "CONTINUE"
    assert result.hard_stop is False
    assert result.directive is None


def test_decreasing_signatures_count_as_progress() -> None:
    state = make_state()
    cfg = RetryGateConfig()
    views = [
        make_view("a", "b", "c"),
        make_view("a", "b"),
        make_view("a"),
    ]
    results = [
        evaluate(state, make_request(views[i], round_index=i + 1), cfg) for i in range(3)
    ]
    assert [r.decision for r in results] == ["CONTINUE", "CONTINUE", "CONTINUE"]
    assert all(r.hard_stop is False for r in results)


def test_three_identical_rounds_warn_with_directive() -> None:
    state = make_state()
    cfg = RetryGateConfig()
    view = make_view("stuck")
    results = [
        evaluate(state, make_request(view, round_index=i), cfg) for i in (1, 2, 3)
    ]
    assert results[0].decision == "CONTINUE"
    assert results[1].decision == "CONTINUE"
    assert results[2].decision == "NO_PROGRESS_WARN"
    assert results[2].hard_stop is False
    assert results[2].directive
    assert "再试一次" not in results[2].directive
    assert "RAG" in results[2].directive or "at:" in results[2].directive


def test_symptoms_and_pointers_excluded_from_signature_set() -> None:
    state = make_state()
    cfg = RetryGateConfig()
    first = make_view("root-a")
    second = make_view(
        "root-a",
        symptoms=("sym-new",),
        pointers=("ptr-new",),
        dropped=("drop-new",),
    )
    assert project_signature_set(first) == project_signature_set(second)

    r1 = evaluate(state, make_request(first, round_index=1), cfg)
    r2 = evaluate(state, make_request(second, round_index=2), cfg)
    assert r1.signature_set == r2.signature_set == frozenset({"root-a"})
    assert r2.decision == "CONTINUE"
    assert state.signature_history[0] == state.signature_history[1]
