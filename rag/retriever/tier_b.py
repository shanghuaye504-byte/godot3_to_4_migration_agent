"""B 层散文检索：两路召回、加权 RRF、上界归一化、阈值、调用 RerankFn。

本文件负责：``query_prose()``。对已有 Lance 表做 BM25 + 向量两次独立查询，
在 Python 里融合。表列不得增删。

禁止：拼 SQL、决定 ``coverage`` / ``escalate_suggested``、在本文件 import 具体
cross-encoder 或写死重排超参、使用 ``embed()`` / ``passage_embed`` 做查询。
调用方：仅 ``router.retrieve``。
被调用方：``rerank`` 的 callable、``observe`` 的 channel/fusion/rerank hook。

对应文档：``rag/retriever/docs/tier-b.md``。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from typing import Any

from rag.bge import EMBEDDING_DIM
from rag.retriever.config import TierBConfig
from rag.retriever.observe import (
    ChannelResultEvent,
    FusionCandidate,
    FusionEvent,
    RerankEvent,
    safe_observe,
)
from rag.retriever.rerank import get_reranker, identity_rerank
from rag.retriever.schemas import ProseChunk, ProseHit

_LOG = logging.getLogger("rag.retriever.tier_b")
_FTS_READY: set[int] = set()
_QUOTE_RE = re.compile(r"[\"']")
_SPACE_RE = re.compile(r"\s+")


def weighted_rrf(
    bm25_ids: Sequence[str],
    vector_ids: Sequence[str],
    *,
    w_bm25: float,
    w_vector: float,
    rrf_k: int,
) -> dict[str, float]:
    """加权 RRF：``s(d) = Σ_i w_i / (rrf_k + rank_i(d))``，rank 从 1 起。"""
    scores: dict[str, float] = {}
    if w_bm25:
        for rank, cid in enumerate(bm25_ids, start=1):
            scores[cid] = scores.get(cid, 0.0) + w_bm25 / (rrf_k + rank)
    if w_vector:
        for rank, cid in enumerate(vector_ids, start=1):
            scores[cid] = scores.get(cid, 0.0) + w_vector / (rrf_k + rank)
    return scores


def rrf_upper_bound(
    *,
    w_bm25: float,
    w_vector: float,
    rrf_k: int,
    channels: str,
) -> float:
    """理论上界 ``Σ_i w_i / (rrf_k + 1)``，只计入本次开启的通道。"""
    total = 0.0
    if channels in ("hybrid", "bm25"):
        total += w_bm25 / (rrf_k + 1)
    if channels in ("hybrid", "vector"):
        total += w_vector / (rrf_k + 1)
    return total


def normalize_rrf(raw: float, s_max: float) -> float:
    if s_max <= 0:
        return 0.0
    score = raw / s_max
    if score < 0:
        return 0.0
    if score > 1:
        return 1.0
    return score


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(x) for x in value]


def _record_to_chunk(row: dict[str, Any]) -> ProseChunk:
    payload = {
        "id": str(row["id"]),
        "text": str(row.get("text") or ""),
        "heading_path": _as_str_list(row.get("heading_path")),
        "since_version": row.get("since_version"),
        "since_version_code": int(row.get("since_version_code") or 0),
        "related_symbols": _as_str_list(row.get("related_symbols")),
        "source": str(row.get("source") or ""),
        "source_file": str(row.get("source_file") or ""),
        "source_url": row.get("source_url"),
    }
    if payload["source_url"] is not None:
        payload["source_url"] = str(payload["source_url"])
        if payload["source_url"] in ("", "None", "null"):
            payload["source_url"] = None
    return ProseChunk.model_validate(payload)


def _row_id(row: dict[str, Any]) -> str:
    return str(row["id"])


def _raw_channel_score(row: dict[str, Any]) -> float | None:
    for key in ("_score", "_relevance_score", "_distance"):
        if key in row and row[key] is not None:
            try:
                return float(row[key])
            except (TypeError, ValueError):
                return None
    return None


def _fts_query_text(text: str) -> str:
    cleaned = _QUOTE_RE.sub(" ", text)
    cleaned = _SPACE_RE.sub(" ", cleaned).strip()
    return cleaned[:500]


def _version_where(target_version_code: int) -> str:
    return f"since_version_code <= {int(target_version_code)}"


def _ensure_fts_index(table: Any) -> None:
    key = id(table)
    if key in _FTS_READY:
        return
    indexed = False
    try:
        indices = table.list_indices()
        for item in indices or []:
            blob = str(item).lower()
            index_type = str(getattr(item, "index_type", "")).upper()
            name = str(getattr(item, "name", "")).lower()
            if "FTS" in blob.upper() or index_type == "FTS" or "fts" in name:
                indexed = True
                break
    except Exception:
        indexed = False
    if not indexed:
        from lancedb.index import FTS

        table.create_index("text", config=FTS())
        _LOG.info("已为 corpus 创建 FTS 索引（只在缺失时写一次）")
    _FTS_READY.add(key)


def _search_fts(table: Any, text: str, k: int, where: str) -> list[dict[str, Any]]:
    _ensure_fts_index(table)
    query = table.search(_fts_query_text(text), query_type="fts").limit(int(k))
    query = query.where(where, prefilter=True)
    return list(query.to_list())


def embed_query(text: str) -> list[float]:
    """对 query 字符串做 ``query_embed``，禁止 ``embed()`` / ``passage_embed``。"""
    from rag.bge import get_text_embedding

    model = get_text_embedding()
    if not hasattr(model, "query_embed"):
        raise ValueError("embedding 模型没有 query_embed，拒绝混用 embed()/passage_embed")
    raw = next(iter(model.query_embed(text)))
    vector = [float(x) for x in raw]
    if len(vector) != EMBEDDING_DIM:
        raise RuntimeError(f"query_embed 期望 {EMBEDDING_DIM} 维，实际 {len(vector)}")
    return vector


def _search_vector(table: Any, text: str, k: int, where: str) -> list[dict[str, Any]]:
    vector = embed_query(text)
    query = table.search(vector, query_type="vector").limit(int(k))
    query = query.where(where, prefilter=True)
    return list(query.to_list())


def _match_reason(cid: str, bm25_ids: Sequence[str], vector_ids: Sequence[str]) -> str:
    in_b = cid in bm25_ids
    in_v = cid in vector_ids
    if in_b and in_v:
        return "hybrid"
    if in_b:
        return "bm25"
    return "vector"


def query_prose(
    table: Any,
    *,
    text: str,
    target_version_code: int,
    config: Any,
    rerank_fn: Callable[[str, Sequence[Any]], Sequence[float]] | None = None,
    observer: Any = None,
    request_id: str | None = None,
    stats: dict[str, Any] | None = None,
) -> list[ProseHit]:
    """Lance 混合检索，返回 ``ProseHit`` 列表。

    ``score`` 永远是 RRF 上界归一化后的 ``[0, 1]``，不是重排分。
    """
    if table is None:
        _LOG.warning("B 层表句柄为空，跳过散文检索")
        return []
    query_text = (text or "").strip()
    if not query_text:
        return []

    tier_b: TierBConfig = (
        config if isinstance(config, TierBConfig) else TierBConfig.model_validate(config)
    )
    channels = tier_b.channels
    where = _version_where(target_version_code)
    fts_text = _fts_query_text(query_text)

    bm25_rows: list[dict[str, Any]] = []
    vector_rows: list[dict[str, Any]] = []
    if channels in ("hybrid", "bm25") and fts_text:
        bm25_rows = _search_fts(table, query_text, tier_b.bm25.k, where)
        safe_observe(
            observer,
            "on_channel_result",
            ChannelResultEvent(
                channel="bm25",
                chunk_ids=[_row_id(r) for r in bm25_rows],
                raw_scores=[_raw_channel_score(r) for r in bm25_rows],
                request_id=request_id,
            ),
        )
    if channels in ("hybrid", "vector"):
        vector_rows = _search_vector(table, query_text, tier_b.vector.k, where)
        safe_observe(
            observer,
            "on_channel_result",
            ChannelResultEvent(
                channel="vector",
                chunk_ids=[_row_id(r) for r in vector_rows],
                raw_scores=[_raw_channel_score(r) for r in vector_rows],
                request_id=request_id,
            ),
        )

    bm25_ids = [_row_id(r) for r in bm25_rows]
    vector_ids = [_row_id(r) for r in vector_rows]
    chunks_by_id: dict[str, ProseChunk] = {}
    for row in bm25_rows + vector_rows:
        cid = _row_id(row)
        if cid not in chunks_by_id:
            chunks_by_id[cid] = _record_to_chunk(row)

    w_bm25 = float(tier_b.bm25.weight) if channels in ("hybrid", "bm25") else 0.0
    w_vector = float(tier_b.vector.weight) if channels in ("hybrid", "vector") else 0.0
    raw_scores = weighted_rrf(
        bm25_ids if w_bm25 else [],
        vector_ids if w_vector else [],
        w_bm25=w_bm25,
        w_vector=w_vector,
        rrf_k=tier_b.fusion.rrf_k,
    )
    s_max = rrf_upper_bound(
        w_bm25=w_bm25,
        w_vector=w_vector,
        rrf_k=tier_b.fusion.rrf_k,
        channels=channels,
    )
    ordered_ids = sorted(raw_scores, key=lambda cid: (-raw_scores[cid], cid))
    ordered_ids = ordered_ids[: tier_b.recall_k]

    bm25_rank = {cid: i for i, cid in enumerate(bm25_ids, start=1)}
    vector_rank = {cid: i for i, cid in enumerate(vector_ids, start=1)}
    normalized: dict[str, float] = {}
    fusion_candidates: list[FusionCandidate] = []
    for cid in ordered_ids:
        score = normalize_rrf(raw_scores[cid], s_max)
        normalized[cid] = score
        fusion_candidates.append(
            FusionCandidate(
                chunk_id=cid,
                rank_bm25=bm25_rank.get(cid),
                rank_vector=vector_rank.get(cid),
                rrf_raw=raw_scores[cid],
                score_normalized=score,
            )
        )

    threshold = tier_b.score_threshold
    kept_ids = list(ordered_ids)
    dropped = 0
    if threshold is not None:
        kept_ids = [cid for cid in ordered_ids if normalized[cid] >= threshold]
        dropped = len(ordered_ids) - len(kept_ids)

    safe_observe(
        observer,
        "on_fusion",
        FusionEvent(
            candidates=fusion_candidates,
            request_id=request_id,
            threshold_dropped=dropped,
        ),
    )

    candidates = [chunks_by_id[cid] for cid in kept_ids if cid in chunks_by_id]
    fn = rerank_fn or get_reranker(tier_b.reranker)
    if fn is None:
        fn = identity_rerank
    rerank_scores = list(fn(query_text, candidates))
    if len(rerank_scores) != len(candidates):
        raise ValueError("RerankFn 必须返回与 candidates 等长的分数")

    paired = list(zip(candidates, rerank_scores, strict=True))
    # 稳定排序：分数相同则保持融合顺序
    paired.sort(key=lambda item: item[1], reverse=True)
    after = [chunk for chunk, _ in paired]
    after_ids = [chunk.id for chunk in after]
    before_ids = [chunk.id for chunk in candidates]
    changed_top1 = bool(before_ids and after_ids and before_ids[0] != after_ids[0])

    safe_observe(
        observer,
        "on_rerank",
        RerankEvent(
            before_ids=before_ids,
            after_ids=after_ids,
            rerank_scores=[float(s) for _, s in paired],
            request_id=request_id,
        ),
    )

    final = after[: tier_b.rerank_k]
    hits = [
        ProseHit(
            chunk=chunk,
            score=normalized[chunk.id],
            match_reason=_match_reason(chunk.id, bm25_ids, vector_ids),  # type: ignore[arg-type]
        )
        for chunk in final
    ]
    if stats is not None:
        stats["threshold_dropped"] = dropped
        stats["rerank_changed_top1"] = changed_top1
        stats["channel_ranks"] = {"bm25": list(bm25_ids), "vector": list(vector_ids)}
    return hits


def reset_fts_cache() -> None:
    """测试用：允许下一张表重新检测 FTS。"""
    _FTS_READY.clear()
