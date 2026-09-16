"""`state_store.InMemoryStateStore` 的纯逻辑测试。

覆盖要点：
- `load()` 对空槽返回全零初始状态（`signature_history=[]`、`rounds_used=0`、
  `circuit_state="CLOSED"`），不抛异常。
- `save()` 之后再 `load()` 能拿到刚保存的状态（含深拷贝：改调用方对象不影响已存快照）。
- 单槽：后一次 `save` 覆盖前一次；两个 `InMemoryStateStore()` 实例互不共享。
"""

from __future__ import annotations

from godot_mcp.verify_gate.models import ProjectVerifyState
from godot_mcp.verify_gate.state_store import InMemoryStateStore, StateStore

from tests.verify_gate.helpers import make_state, make_view


def test_load_empty_slot_returns_empty_state() -> None:
    store = InMemoryStateStore()
    state = store.load()
    assert state.signature_history == []
    assert state.per_file_patch_count == {}
    assert state.per_file_last_signature_set == {}
    assert state.infra_failure_streak == 0
    assert state.rounds_used == 0
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
    original.infra_failure_streak = 1

    store.save(original)
    original.per_file_patch_count["res://player.gd"] = 99
    original.signature_history.append(frozenset({"mutated"}))

    loaded = store.load()
    assert loaded.rounds_used == 2
    assert loaded.infra_failure_streak == 1
    assert loaded.per_file_patch_count["res://player.gd"] == 2
    assert loaded.per_file_last_signature_set["res://player.gd"] == frozenset({"sig-a"})
    assert loaded.signature_history == [frozenset({"sig-a"})]

    loaded.per_file_patch_count["res://player.gd"] = 7
    loaded_again = store.load()
    assert loaded_again.per_file_patch_count["res://player.gd"] == 2


def test_save_overwrites_single_slot() -> None:
    store = InMemoryStateStore()
    first = make_state()
    first.per_file_patch_count["res://a.gd"] = 3
    store.save(first)

    second = make_state()
    second.per_file_patch_count["res://b.gd"] = 1
    store.save(second)

    loaded = store.load()
    assert loaded.per_file_patch_count == {"res://b.gd": 1}


def test_two_store_instances_do_not_share_state() -> None:
    a_store = InMemoryStateStore()
    b_store = InMemoryStateStore()
    a = make_state()
    a.per_file_patch_count["res://a.gd"] = 3
    a_store.save(a)

    assert b_store.load().per_file_patch_count == {}
    b = make_state()
    b.per_file_patch_count["res://b.gd"] = 1
    b_store.save(b)

    assert a_store.load().per_file_patch_count == {"res://a.gd": 3}
    assert b_store.load().per_file_patch_count == {"res://b.gd": 1}


def test_snapshot_and_previous_view_round_trip_and_copy() -> None:
    store = InMemoryStateStore()
    original = make_state()
    original.source_snapshot["a.gd"] = "class_name Foo\n"
    original.previous_view = make_view("sig-root")
    store.save(original)

    original.source_snapshot["a.gd"] = "mutated"
    assert original.previous_view is not None
    original.previous_view.caveats.append("mutated-caveat")

    loaded = store.load()
    assert loaded.source_snapshot == {"a.gd": "class_name Foo\n"}
    assert loaded.previous_view is not None
    assert [e.local_signature for e in loaded.previous_view.root_cause_errors] == ["sig-root"]
    assert loaded.previous_view.caveats == []

    loaded.source_snapshot["a.gd"] = "other"
    loaded_again = store.load()
    assert loaded_again.source_snapshot["a.gd"] == "class_name Foo\n"


def test_in_memory_store_satisfies_protocol() -> None:
    store: StateStore = InMemoryStateStore()
    state = store.load()
    assert isinstance(state, ProjectVerifyState)
    store.save(state)
