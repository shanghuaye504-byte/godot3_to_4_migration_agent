"""检索观测 hook。默认 NoOp，但 router 每阶段仍调用。

本文件负责：``RetrievalObserver`` 协议、``NoOpObserver``、``CompositeObserver``、
进程级 ``set_observer`` / ``get_observer``，以及事件对象（普通 dataclass，
不是 Agent 契约）。

禁止：做检索、默认写远端、import ``tier_b`` / ``tier_a`` 去反查库。
调用方：仅 ``router.retrieve``（以及 ``query_prose`` 经 router 传入的 observer）。
被调用方：自定义 sink（由调用方提供）。

对应文档：``rag/retriever/docs/observability.md``。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

_LOG = logging.getLogger("rag.retriever.observe")


@dataclass
class RetrieveStartEvent:
    request_id: str | None
    config_snapshot: dict[str, Any]
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ChannelResultEvent:
    channel: str
    chunk_ids: list[str]
    raw_scores: list[float | None] = field(default_factory=list)
    request_id: str | None = None


@dataclass
class FusionCandidate:
    chunk_id: str
    rank_bm25: int | None
    rank_vector: int | None
    rrf_raw: float
    score_normalized: float


@dataclass
class FusionEvent:
    candidates: list[FusionCandidate]
    request_id: str | None = None
    threshold_dropped: int = 0


@dataclass
class RerankEvent:
    before_ids: list[str]
    after_ids: list[str]
    rerank_scores: list[float]
    request_id: str | None = None


@dataclass
class RetrievalTraceEvent:
    request_id: str | None
    ts: str
    query_digest: dict[str, Any]
    config_snapshot: dict[str, Any]
    resolved_symbols: list[str]
    structured_hits: list[dict[str, Any]]
    prose_hits: list[dict[str, Any]]
    coverage: str
    recommended_action: str | None
    escalate_suggested: bool
    cache_hit: bool
    took_ms: float
    threshold_dropped: int = 0
    channel_ranks: dict[str, list[str]] = field(default_factory=dict)
    rerank_changed_top1: bool = False


@dataclass
class TierAErrorEvent:
    event: str
    error_type: str | None
    error_message: str | None
    rule_id: str | None = None
    row_excerpt: str | None = None
    symbols: list[str] | None = None
    target_version_code: int | None = None
    request_id: str | None = None


class RetrievalObserver(Protocol):
    """检索各阶段的回调。不关心的方法保持空即可。"""

    def on_retrieve_start(self, event: Any) -> None: ...

    def on_channel_result(self, event: Any) -> None: ...

    def on_fusion(self, event: Any) -> None: ...

    def on_rerank(self, event: Any) -> None: ...

    def on_retrieve_end(self, event: Any) -> None: ...

    def on_tier_a_error(self, event: Any) -> None: ...

    def on_schema_skip(self, event: Any) -> None: ...


class NoOpObserver:
    """默认观察者：所有方法什么都不做。router 在未注入时必须使用这个。"""

    def on_retrieve_start(self, event: Any) -> None:
        return None

    def on_channel_result(self, event: Any) -> None:
        return None

    def on_fusion(self, event: Any) -> None:
        return None

    def on_rerank(self, event: Any) -> None:
        return None

    def on_retrieve_end(self, event: Any) -> None:
        return None

    def on_tier_a_error(self, event: Any) -> None:
        return None

    def on_schema_skip(self, event: Any) -> None:
        return None


def _call_one(observer: Any, method: str, event: Any) -> None:
    fn = getattr(observer, method, None)
    if fn is None:
        return
    try:
        fn(event)
    except Exception:
        _LOG.exception("observer %r 的 %s 抛错，已吞掉以免打断检索", observer, method)


class CompositeObserver:
    """按顺序转发到多个 observer。某个 sink 抛错不得打断检索。"""

    def __init__(self, observers: list[Any]) -> None:
        self._observers = list(observers)

    def on_retrieve_start(self, event: Any) -> None:
        for obs in self._observers:
            _call_one(obs, "on_retrieve_start", event)

    def on_channel_result(self, event: Any) -> None:
        for obs in self._observers:
            _call_one(obs, "on_channel_result", event)

    def on_fusion(self, event: Any) -> None:
        for obs in self._observers:
            _call_one(obs, "on_fusion", event)

    def on_rerank(self, event: Any) -> None:
        for obs in self._observers:
            _call_one(obs, "on_rerank", event)

    def on_retrieve_end(self, event: Any) -> None:
        for obs in self._observers:
            _call_one(obs, "on_retrieve_end", event)

    def on_tier_a_error(self, event: Any) -> None:
        for obs in self._observers:
            _call_one(obs, "on_tier_a_error", event)

    def on_schema_skip(self, event: Any) -> None:
        for obs in self._observers:
            _call_one(obs, "on_schema_skip", event)


_process_observer: Any = NoOpObserver()


def set_observer(observer: Any) -> None:
    """进程级默认 observer。worker 启动时调用一次。测试结束应设回 NoOp。"""
    global _process_observer
    _process_observer = observer if observer is not None else NoOpObserver()


def get_observer() -> Any:
    """返回进程级默认值；尚未 ``set_observer`` 时应为 ``NoOpObserver``。"""
    return _process_observer


def safe_observe(observer: Any, method: str, event: Any) -> None:
    """router / tier_b 统一入口：observer 抛错不得打断检索。"""
    if observer is None:
        return
    _call_one(observer, method, event)
