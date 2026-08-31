"""Router：抠符号、覆盖率、A 失败降级、缓存、observer。"""

from __future__ import annotations

import sqlite3
from typing import Any

from pathlib import Path

from rag.retriever.cache import cache_key, retrieve_cached
from rag.retriever.config import RetrieverConfig, config_hash
from rag.retriever.observe import CompositeObserver, NoOpObserver, get_observer, set_observer
from rag.retriever.rerank import get_reranker, identity_rerank, minilm_l6_rerank
from rag.retriever.router import (
    RuntimeHandles,
    extract_symbols,
    retrieve,
    set_handles,
)
from rag.retriever.schemas import (
    AgentAction,
    RetrievalMode,
    RetrievalQuery,
)
from test_retriever_tier_a import _conn, _insert


class RecordingObserver:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def on_retrieve_start(self, event: Any) -> None:
        self.calls.append("start")

    def on_channel_result(self, event: Any) -> None:
        self.calls.append(f"channel:{event.channel}")

    def on_fusion(self, event: Any) -> None:
        self.calls.append("fusion")

    def on_rerank(self, event: Any) -> None:
        self.calls.append("rerank")

    def on_retrieve_end(self, event: Any) -> None:
        self.calls.append("end")

    def on_tier_a_error(self, event: Any) -> None:
        self.calls.append("a_error")

    def on_schema_skip(self, event: Any) -> None:
        self.calls.append("skip")


def _bind(conn: sqlite3.Connection, table: Any = None) -> None:
    set_handles(
        RuntimeHandles(
            conn=conn,
            table=table,
            artifacts_dir=Path("."),
            manifest_hash="test-manifest",
            config=RetrieverConfig(),
        )
    )


def test_extract_symbols() -> None:
    text = (
        "SCRIPT ERROR: Invalid call. Nonexistent function 'instance' "
        "in base 'PackedScene'."
    )
    assert "instance" in extract_symbols(text)
    assert extract_symbols('Identifier "GameState" not found') == ["GameState"]
    assert extract_symbols("Invalid get index 'extents'") == ["extents"]
    assert "Tween" in extract_symbols("see `Tween` in docs")
    assert extract_symbols("") == []


def test_query_validation_requires_input() -> None:
    import pytest

    with pytest.raises(Exception):
        RetrievalQuery(target_version="4.7.1")
    with pytest.raises(Exception):
        RetrievalQuery(symbols=["x"], target_version="4.7-rc1")


def test_retrieve_exact_only_rule_hit() -> None:
    conn = _conn()
    _insert(
        conn,
        id="official_renames_skipped:instance",
        old_symbol="instance",
        new_symbol="instantiate",
        source="official_renames_skipped",
        agent_action="apply_and_warn",
        converter_gap=1,
    )
    _bind(conn)
    result = retrieve(
        RetrievalQuery(
            error_text="Nonexistent function 'instance' in base 'PackedScene'.",
            symbols=["instance"],
            target_version="4.7.1",
            retrieval_mode=RetrievalMode.exact_only,
        )
    )
    assert result.coverage == "rule_hit"
    assert result.escalate_suggested is False
    assert result.recommended_action == AgentAction.apply_and_warn
    assert result.structured_hits[0].rule.new_symbol == "instantiate"
    assert result.structured_hits[0].match_reason == "old_symbol"
    assert result.merged[0].layer == "A"
    assert result.prose_hits == []
    assert result.cache_hit is False
    assert result.target_version_code == 40701


def test_no_hit_suggests_escalate() -> None:
    conn = _conn()
    _bind(conn)
    result = retrieve(
        RetrievalQuery(
            symbols=["definitely_not_in_db"],
            target_version="4.7.1",
            retrieval_mode=RetrievalMode.exact_only,
        )
    )
    assert result.coverage == "no_hit"
    assert result.escalate_suggested is True
    assert result.recommended_action is None


def test_a_failure_degrades_and_continues(monkeypatch) -> None:
    conn = _conn()
    _bind(conn)

    def boom(*args: Any, **kwargs: Any) -> list:
        raise sqlite3.DatabaseError("corrupt")

    monkeypatch.setattr("rag.retriever.router.query_rules", boom)
    obs = RecordingObserver()
    result = retrieve(
        RetrievalQuery(
            symbols=["instance"],
            target_version="4.7.1",
            retrieval_mode=RetrievalMode.hybrid,
        ),
        observer=obs,
    )
    assert result.structured_hits == []
    assert "a_error" in obs.calls
    assert "end" in obs.calls
    assert "start" in obs.calls


def test_merged_a_before_b(monkeypatch) -> None:
    conn = _conn()
    _insert(conn, id="r1", old_symbol="instance", new_symbol="instantiate")
    _bind(conn)

    from rag.retriever.schemas import ProseChunk, ProseHit

    fake = [
        ProseHit(
            chunk=ProseChunk(
                id="c1",
                text="notes",
                heading_path=["h"],
                source="official_doc",
                source_file="x.rst",
            ),
            score=0.4,
            match_reason="bm25",
        )
    ]
    monkeypatch.setattr("rag.retriever.router.query_prose", lambda *a, **k: fake)
    result = retrieve(
        RetrievalQuery(symbols=["instance"], target_version="4.7.1")
    )
    assert [h.layer for h in result.merged] == ["A", "B"]
    assert result.coverage == "rule_hit"


def test_cache_excludes_request_id_and_sets_flag() -> None:
    conn = _conn()
    _insert(conn, id="r1", old_symbol="instance", new_symbol="instantiate")
    _bind(conn)
    q1 = RetrievalQuery(
        symbols=["instance"],
        target_version="4.7.1",
        retrieval_mode=RetrievalMode.exact_only,
        request_id="job-A",
    )
    q2 = RetrievalQuery(
        symbols=["instance"],
        target_version="4.7.1",
        retrieval_mode=RetrievalMode.exact_only,
        request_id="job-B",
    )
    cfg = RetrieverConfig()
    assert cache_key(q1, "m", config_hash(cfg)) == cache_key(q2, "m", config_hash(cfg))
    first = retrieve_cached(q1, config=cfg)
    second = retrieve_cached(q2, config=cfg)
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.structured_hits[0].rule.id == first.structured_hits[0].rule.id
    assert second.coverage == first.coverage


def test_identity_rerank_and_unknown_name() -> None:
    chunks = [object(), object(), object()]
    scores = identity_rerank("q", chunks)
    assert list(scores) == [0.0, 0.0, 0.0]
    assert get_reranker("identity") is identity_rerank
    assert get_reranker("minilm_l6") is minilm_l6_rerank
    try:
        get_reranker("missing")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass


def test_minilm_l6_rerank_uses_stub_encoder(monkeypatch) -> None:
    from types import SimpleNamespace

    class FakeEncoder:
        def rerank(self, query, documents, batch_size=32, **kwargs):
            assert query == "yield to await"
            assert batch_size == 32
            return [float(len(doc)) for doc in documents]

    monkeypatch.setattr("rag.retriever.rerank._get_cross_encoder", lambda: FakeEncoder())
    chunks = [
        SimpleNamespace(text="aa", heading_path=["Signals"]),
        SimpleNamespace(text="bbbb", heading_path=[]),
    ]
    scores = minilm_l6_rerank("yield to await", chunks)
    assert scores[0] == float(len("Signals\n\naa"))
    assert scores[1] == 4.0
    assert list(minilm_l6_rerank("q", [])) == []


def test_composite_swallows_errors() -> None:
    class Boom:
        def on_retrieve_end(self, event: Any) -> None:
            raise RuntimeError("sink down")

    quiet = RecordingObserver()
    CompositeObserver([Boom(), quiet]).on_retrieve_end(object())
    assert "end" in quiet.calls


def test_set_get_observer() -> None:
    obs = RecordingObserver()
    set_observer(obs)
    assert get_observer() is obs
    set_observer(NoOpObserver())
    assert isinstance(get_observer(), NoOpObserver)
