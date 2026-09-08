"""`state_store.InMemoryStateStore` 的纯逻辑测试 —— 方案文档 §3"存在哪里"。

覆盖要点：
- `load()` 对从未见过的 `(workspace_id, session_id)` 返回一个全零初始状态
  （`signature_history=[]`、`rounds_used=0`、`cost_used_usd=0.0`、
  `circuit_state="CLOSED"`），不抛异常。
- `save()` 之后再 `load()` 同一个 `(workspace_id, session_id)`，能拿到刚保存的状态
  （字段逐一核对，包括 `per_file_patch_count`/`per_file_last_signature_set` 这两个
  字典类型字段，确认不是浅拷贝导致的引用共享 bug）。
- 不同 `(workspace_id, session_id)` 的状态互不干扰（同一个 `workspace_id` 但不同
  `session_id` 时，`per_file_patch_count` 等状态不应该串到另一个会话里）。
- `StateStore` 协议：`InMemoryStateStore` 满足 `load`/`save` 两个方法签名，可以直接
  传给依赖 `StateStore` 协议的调用方（鸭子类型检查，不需要显式继承）。
"""

from __future__ import annotations

from godot_mcp.verify_gate.models import ProjectVerifyState
from godot_mcp.verify_gate.state_store import InMemoryStateStore, StateStore

from tests.verify_gate.helpers import make_state, make_view


def test_load_unknown_session_returns_empty_state() -> None:
    store = InMemoryStateStore()
    state = store.load("ws-new", "sess-new")
    assert state.workspace_id == "ws-new"
    assert state.session_id == "sess-new"
    assert state.signature_history == []
    assert state.per_file_patch_count == {}
    assert state.per_file_last_signature_set == {}
    assert state.infra_failure_streak == 0
    assert state.rounds_used == 0
    assert state.cost_used_usd == 0.0
    assert state.circuit_state == "CLOSED"
    assert state.previous_view is None
    assert state.source_snapshot == {}


def test_save_then_load_round_trips_and_copies() -> None:
    store = InMemoryStateStore()
    original = make_state()
    original.signature_history.append(frozenset({"sig-a"}))
    original.per_file_patch_count["res://player.gd"] = 2
    original.per_file_last_signature_set["res://player.gd"] = frozenset({"sig-a"})
    original.rounds_used = 2
    original.cost_used_usd = 0.4
    original.infra_failure_streak = 1

    store.save(original)
    original.per_file_patch_count["res://player.gd"] = 99
    original.signature_history.append(frozenset({"mutated"}))

    loaded = store.load("ws-1", "sess-1")
    assert loaded.rounds_used == 2
    assert loaded.cost_used_usd == 0.4
    assert loaded.infra_failure_streak == 1
    assert loaded.per_file_patch_count["res://player.gd"] == 2
    assert loaded.per_file_last_signature_set["res://player.gd"] == frozenset({"sig-a"})
    assert loaded.signature_history == [frozenset({"sig-a"})]

    loaded.per_file_patch_count["res://player.gd"] = 7
    loaded_again = store.load("ws-1", "sess-1")
    assert loaded_again.per_file_patch_count["res://player.gd"] == 2


def test_sessions_do_not_interfere() -> None:
    store = InMemoryStateStore()
    a = make_state(session_id="sess-a")
    a.per_file_patch_count["res://a.gd"] = 3
    store.save(a)

    b = store.load("ws-1", "sess-b")
    assert b.per_file_patch_count == {}
    b.per_file_patch_count["res://b.gd"] = 1
    store.save(b)

    assert store.load("ws-1", "sess-a").per_file_patch_count == {"res://a.gd": 3}
    assert store.load("ws-1", "sess-b").per_file_patch_count == {"res://b.gd": 1}


def test_snapshot_and_previous_view_round_trip_and_copy() -> None:
    store = InMemoryStateStore()
    original = make_state()
    original.source_snapshot["a.gd"] = "class_name Foo\n"
    original.previous_view = make_view("sig-root")
    store.save(original)

    original.source_snapshot["a.gd"] = "mutated"
    assert original.previous_view is not None
    original.previous_view.caveats.append("mutated-caveat")

    loaded = store.load("ws-1", "sess-1")
    assert loaded.source_snapshot == {"a.gd": "class_name Foo\n"}
    assert loaded.previous_view is not None
    assert [e.local_signature for e in loaded.previous_view.root_cause_errors] == ["sig-root"]
    assert loaded.previous_view.caveats == []

    loaded.source_snapshot["a.gd"] = "other"
    loaded_again = store.load("ws-1", "sess-1")
    assert loaded_again.source_snapshot["a.gd"] == "class_name Foo\n"


def test_snapshots_do_not_leak_across_sessions() -> None:
    store = InMemoryStateStore()
    a = make_state(session_id="sess-a")
    a.source_snapshot["a.gd"] = "A"
    store.save(a)

    b = store.load("ws-1", "sess-b")
    assert b.source_snapshot == {}
    b.source_snapshot["b.gd"] = "B"
    store.save(b)

    assert store.load("ws-1", "sess-a").source_snapshot == {"a.gd": "A"}
    assert store.load("ws-1", "sess-b").source_snapshot == {"b.gd": "B"}


def test_in_memory_store_satisfies_protocol() -> None:
    store: StateStore = InMemoryStateStore()
    state = store.load("ws", "sess")
    assert isinstance(state, ProjectVerifyState)
    store.save(state)
