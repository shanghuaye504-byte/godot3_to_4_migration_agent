"""`ProjectVerifyState` 的读写接口 —— 方案文档 §3"存在哪里"。

判定算法（`algorithm.py`）不应该依赖状态具体存在哪里，只依赖"能读到
`ProjectVerifyState`，能写回去"这个接口。先给内存实现，接口留好之后再补 Redis 实现。

- **单 worker、单会话场景**（当前阶段够用）：进程内内存字典，
  `{(workspace_id, session_id): ProjectVerifyState}`，会话结束即释放。
- **多 worker、需要跨进程共享场景**（分布式阶段）：Redis，key 设计为
  `verify_state:{workspace_id}:{session_id}`，`signature_history` 整体序列化成 JSON
  存 String（历史轮次不会太长，几十轮封顶，没必要拆分成 Redis 原生结构）。
  `circuit_state` 单独用一个带 TTL 的 key（`circuit:{workspace_id}`），方便熔断状态
  在没有活跃会话时也能被其它 worker 看到（工作区级熔断需要跨会话生效）。
"""

from __future__ import annotations

from typing import Protocol

from godot_mcp.verify_filter.models import ProjectFilterView
from godot_mcp.verify_gate.models import ProjectVerifyState


class StateStore(Protocol):
    """`algorithm.evaluate()` 唯一依赖的状态读写协议，内存/Redis 实现都满足这个接口。"""

    def load(self, workspace_id: str, session_id: str) -> ProjectVerifyState:
        """读取（或首次创建）指定会话的状态。不存在时返回一个全零初始状态，不抛异常。"""
        ...

    def save(self, state: ProjectVerifyState) -> None:
        """把状态写回存储。调用方（`algorithm.evaluate()` 的外层编排代码）负责在每次
        判定之后调用一次，保证跨轮次的记账不会丢失。"""
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
        workspace_id=state.workspace_id,
        session_id=state.session_id,
        signature_history=list(state.signature_history),
        per_file_patch_count=dict(state.per_file_patch_count),
        per_file_last_signature_set=dict(state.per_file_last_signature_set),
        infra_failure_streak=state.infra_failure_streak,
        rounds_used=state.rounds_used,
        cost_used_usd=state.cost_used_usd,
        circuit_state=state.circuit_state,
        previous_view=_clone_view(state.previous_view),
        source_snapshot=dict(state.source_snapshot),
    )


def _empty_state(workspace_id: str, session_id: str) -> ProjectVerifyState:
    return ProjectVerifyState(
        workspace_id=workspace_id,
        session_id=session_id,
        signature_history=[],
        per_file_patch_count={},
        per_file_last_signature_set={},
        infra_failure_streak=0,
        rounds_used=0,
        cost_used_usd=0.0,
        circuit_state="CLOSED",
        previous_view=None,
        source_snapshot={},
    )


class InMemoryStateStore:
    """单 worker、单会话场景的默认实现：进程内字典，无持久化、无跨进程共享。"""

    def __init__(self) -> None:
        self._states: dict[tuple[str, str], ProjectVerifyState] = {}

    def load(self, workspace_id: str, session_id: str) -> ProjectVerifyState:
        stored = self._states.get((workspace_id, session_id))
        if stored is None:
            return _empty_state(workspace_id, session_id)
        return _clone_state(stored)

    def save(self, state: ProjectVerifyState) -> None:
        self._states[(state.workspace_id, state.session_id)] = _clone_state(state)


class RedisStateStore:
    """多 worker 场景的实现骨架：先占位接口，具体 Redis 客户端与序列化格式在实现阶段确定。

    不在这里定死 Redis 连接细节——这属于"外壳/基础设施选型"，判定算法（`algorithm.py`）
    不应该依赖状态具体存在哪里，只依赖 `StateStore` 协议。
    """

    def __init__(self, *, redis_url: str) -> None:
        self.redis_url = redis_url

    def load(self, workspace_id: str, session_id: str) -> ProjectVerifyState:
        raise NotImplementedError("RedisStateStore 尚未实现")

    def save(self, state: ProjectVerifyState) -> None:
        raise NotImplementedError("RedisStateStore 尚未实现")
