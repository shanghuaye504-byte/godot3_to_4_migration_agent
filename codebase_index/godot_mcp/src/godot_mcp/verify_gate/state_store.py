"""`ProjectVerifyState` 的读写接口 —— 方案文档 §3"存在哪里"。

判定算法（`algorithm.py`）不应该依赖状态具体存在哪里，只依赖"能读到
`ProjectVerifyState`，能写回去"这个接口。

studio / stdio 一对一：进程内至多一份 state，没有 `(workspace_id, session_id)` 复合键。
MCP 进程退出即清空。Redis / 多 worker 不在当前范围；`RedisStateStore` 只留接口占位。
"""

from __future__ import annotations

from typing import Protocol

from godot_mcp.verify_filter.models import ProjectFilterView
from godot_mcp.verify_gate.models import ProjectVerifyState


class StateStore(Protocol):
    """`algorithm.evaluate()` 唯一依赖的状态读写协议。"""

    def load(self) -> ProjectVerifyState:
        """读取当前唯一槽位。没有则返回全零初始状态，不抛异常。"""
        ...

    def save(self, state: ProjectVerifyState) -> None:
        """把状态写回唯一槽位。调用方在每次判定之后调用一次。"""
        ...


def _clone_view(view: ProjectFilterView | None) -> ProjectFilterView | None:
    if view is None:
        return None
    return ProjectFilterView(
        status=view.status,
        root_cause_errors=list(view.root_cause_errors),
        pending_pointers=list(view.pending_pointers),
        symptoms=list(view.symptoms),
        dropped=list(view.dropped),
        caveats=list(view.caveats),
        untrusted_files=frozenset(view.untrusted_files),
        gdscript_complete=view.gdscript_complete,
        shader_checked=view.shader_checked,
    )


def _clone_state(state: ProjectVerifyState) -> ProjectVerifyState:
    """深拷贝可变字段，避免调用方就地改 dict/list 污染已保存的快照。"""
    return ProjectVerifyState(
        signature_history=list(state.signature_history),
        per_file_patch_count=dict(state.per_file_patch_count),
        per_file_last_signature_set=dict(state.per_file_last_signature_set),
        infra_failure_streak=state.infra_failure_streak,
        rounds_used=state.rounds_used,
        circuit_state=state.circuit_state,
        previous_view=_clone_view(state.previous_view),
        source_snapshot=dict(state.source_snapshot),
    )


def _empty_state() -> ProjectVerifyState:
    return ProjectVerifyState(
        signature_history=[],
        per_file_patch_count={},
        per_file_last_signature_set={},
        infra_failure_streak=0,
        rounds_used=0,
        circuit_state="CLOSED",
        previous_view=None,
        source_snapshot={},
    )


class InMemoryStateStore:
    """studio 默认实现：进程内单槽，无持久化、无跨进程共享。"""

    def __init__(self) -> None:
        self._state: ProjectVerifyState | None = None

    def load(self) -> ProjectVerifyState:
        if self._state is None:
            return _empty_state()
        return _clone_state(self._state)

    def save(self, state: ProjectVerifyState) -> None:
        self._state = _clone_state(state)


class RedisStateStore:
    """多 worker 占位。当前 studio 模式不实现。"""

    def __init__(self, *, redis_url: str) -> None:
        self.redis_url = redis_url

    def load(self) -> ProjectVerifyState:
        raise NotImplementedError("RedisStateStore 尚未实现")

    def save(self, state: ProjectVerifyState) -> None:
        raise NotImplementedError("RedisStateStore 尚未实现")
