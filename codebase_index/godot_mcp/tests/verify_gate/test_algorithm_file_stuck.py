"""`algorithm.evaluate()` 的单文件卡住检测测试 —— 方案文档 §4.2 第 5 条、§8 的
G-FILESTUCK / G-FILESTUCK-RESET。

覆盖要点：
- G-FILESTUCK：同一文件被 `patched_files` 命中 `file_stuck_threshold`（默认 3）次，
  且每次涉及的签名集合都相同 → `decision="FILE_STUCK_WARN"`，`directive` 指向"换一种
  排查手段"而不是"再改一次"。
- G-FILESTUCK-RESET（补齐的关键回归测试，对应任务 1 第 4 条修复）：同一文件前两次
  patch 后签名不变，第三次 patch 后签名**变了**（说明这次改动产生了效果），第四、
  五次又不变 → 断言第三次之后 `per_file_patch_count[f]` 被重置为 1，第四、五次不会
  因为"历史上曾经被碰过 3 次"就误触发 `FILE_STUCK_WARN`；只有从签名变化的那一刻重新
  计数满 `file_stuck_threshold` 次才应该再次触发。
- 反例：文件被 patch 次数达到阈值，但每次签名集合都不同 → 不触发 `FILE_STUCK_WARN`
  （"卡住"必须同时满足"次数达标"与"签名未变"两个条件，缺一不可）。
"""

from __future__ import annotations

from godot_mcp.verify_gate.algorithm import evaluate
from godot_mcp.verify_gate.config import RetryGateConfig

from tests.verify_gate.helpers import make_request, make_state, make_view

_FILE = "res://player.gd"


def test_same_file_same_signature_three_times_warns() -> None:
    state = make_state()
    # 把无进展窗口拉开，否则 3 轮相同签名会先命中 NO_PROGRESS_WARN
    cfg = RetryGateConfig(no_progress_window=10)
    view = make_view("stuck")
    results = [
        evaluate(
            state,
            make_request(view, patched_files=frozenset({_FILE})),
            cfg,
        )
        for i in (1, 2, 3)
    ]
    assert results[0].decision == "CONTINUE"
    assert results[1].decision == "CONTINUE"
    assert results[2].decision == "FILE_STUCK_WARN"
    assert results[2].hard_stop is False
    assert results[2].directive
    assert "再改一次" not in results[2].directive
    assert state.per_file_patch_count[_FILE] == 3


def test_signature_change_resets_file_counter() -> None:
    state = make_state()
    cfg = RetryGateConfig(no_progress_window=10)
    s0 = make_view("s0")
    s1 = make_view("s1")

    evaluate(state, make_request(s0, patched_files=frozenset({_FILE})), cfg)
    evaluate(state, make_request(s0, patched_files=frozenset({_FILE})), cfg)
    assert state.per_file_patch_count[_FILE] == 2

    third = evaluate(
        state, make_request(s1, patched_files=frozenset({_FILE})), cfg
    )
    assert third.decision == "CONTINUE"
    assert state.per_file_patch_count[_FILE] == 1

    fourth = evaluate(
        state, make_request(s1, patched_files=frozenset({_FILE})), cfg
    )
    fifth = evaluate(
        state, make_request(s1, patched_files=frozenset({_FILE})), cfg
    )
    assert fourth.decision == "CONTINUE"
    assert fifth.decision == "FILE_STUCK_WARN"
    assert state.per_file_patch_count[_FILE] == 3


def test_changing_signatures_never_count_as_stuck() -> None:
    state = make_state()
    cfg = RetryGateConfig(no_progress_window=10)
    views = [make_view("a"), make_view("b"), make_view("c")]
    results = [
        evaluate(
            state,
            make_request(views[i], patched_files=frozenset({_FILE})),
            cfg,
        )
        for i in range(3)
    ]
    assert all(r.decision == "CONTINUE" for r in results)
    assert state.per_file_patch_count[_FILE] == 1
