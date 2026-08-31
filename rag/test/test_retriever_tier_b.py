"""B 层：加权 RRF、上界归一化、match_reason、阈值。"""

from __future__ import annotations

from typing import Any

from rag.retriever.config import TierBConfig
from rag.retriever.schemas import ProseChunk
from rag.retriever.tier_b import (
    normalize_rrf,
    query_prose,
    rrf_upper_bound,
    weighted_rrf,
)


def test_rrf_both_rank1_is_one() -> None:
    scores = weighted_rrf(["a"], ["a"], w_bm25=1.0, w_vector=1.0, rrf_k=60)
    s_max = rrf_upper_bound(w_bm25=1.0, w_vector=1.0, rrf_k=60, channels="hybrid")
    assert normalize_rrf(scores["a"], s_max) == 1.0


def test_rrf_one_channel_rank1_is_half() -> None:
    scores = weighted_rrf(["a"], [], w_bm25=1.0, w_vector=1.0, rrf_k=60)
    s_max = rrf_upper_bound(w_bm25=1.0, w_vector=1.0, rrf_k=60, channels="hybrid")
    assert abs(normalize_rrf(scores["a"], s_max) - 0.5) < 1e-9


def test_single_channel_bound() -> None:
    scores = weighted_rrf(["a"], [], w_bm25=1.0, w_vector=0.0, rrf_k=60)
    s_max = rrf_upper_bound(w_bm25=1.0, w_vector=0.0, rrf_k=60, channels="bm25")
    assert normalize_rrf(scores["a"], s_max) == 1.0


def _chunk(i: str, text: str) -> dict[str, Any]:
    vec = [float(ord(i[0]) % 7)] + [0.0] * 383
    return {
        "id": i,
        "vector": vec,
        "text": text,
        "heading_path": ["Demo"],
        "since_version": "4.0",
        "since_version_code": 40000,
        "related_symbols": ["yield"],
        "source": "official_doc",
        "source_file": "demo.rst",
        "source_url": None,
    }


def test_query_prose_hybrid_tmp_lance(tmp_path, monkeypatch) -> None:
    import lancedb

    db = lancedb.connect(str(tmp_path))
    rows = [
        _chunk("a", "yield must become await in Godot 4 coroutines"),
        _chunk("b", "PackedScene.instance is now instantiate"),
        _chunk("c", "unrelated paragraph about lighting"),
    ]
    table = db.create_table("corpus", rows)
    from lancedb.index import FTS

    table.create_index("text", config=FTS())

    def fake_embed(text: str) -> list[float]:
        # 让向量路更接近 b（instantiate）
        del text
        return rows[1]["vector"]

    monkeypatch.setattr("rag.retriever.tier_b.embed_query", fake_embed)

    cfg = TierBConfig(
        channels="hybrid",
        recall_k=10,
        rerank_k=3,
        score_threshold=None,
    )
    hits = query_prose(
        table,
        text="Nonexistent function 'instance'",
        target_version_code=40701,
        config=cfg,
    )
    assert hits
    assert all(0.0 <= h.score <= 1.0 for h in hits)
    assert all(h.match_reason in {"bm25", "vector", "hybrid"} for h in hits)
    assert all(isinstance(h.chunk, ProseChunk) for h in hits)


def test_query_prose_version_prefilter(tmp_path, monkeypatch) -> None:
    import lancedb

    db = lancedb.connect(str(tmp_path))
    old = _chunk("old", "yield await coroutine basics")
    future = _chunk("future", "yield await coroutine basics")
    future["since_version"] = "4.9"
    future["since_version_code"] = 40900
    table = db.create_table("corpus", [old, future])
    from lancedb.index import FTS

    table.create_index("text", config=FTS())
    monkeypatch.setattr("rag.retriever.tier_b.embed_query", lambda text: old["vector"])
    cfg = TierBConfig(channels="bm25", rerank_k=5, recall_k=5)
    hits = query_prose(
        table,
        text="yield await coroutine",
        target_version_code=40701,
        config=cfg,
    )
    ids = [h.chunk.id for h in hits]
    assert "old" in ids
    assert "future" not in ids


def test_score_threshold_drops_before_rerank(tmp_path, monkeypatch) -> None:
    import lancedb

    db = lancedb.connect(str(tmp_path))
    rows = [
        _chunk("a", "yield await"),
        _chunk("z", "zzzzzz totally unrelated tokens xyz"),
    ]
    table = db.create_table("corpus", rows)
    from lancedb.index import FTS

    table.create_index("text", config=FTS())
    monkeypatch.setattr("rag.retriever.tier_b.embed_query", lambda text: rows[0]["vector"])
    cfg = TierBConfig(channels="bm25", rerank_k=5, recall_k=10, score_threshold=0.99)
    hits = query_prose(table, text="yield await", target_version_code=40701, config=cfg)
    # 阈值极高时，只有接近理论上界的候选能留下
    assert all(h.score >= 0.99 for h in hits)
