"""统一检索入口：抠符号、调 A、调 B、订 RetrievalResult、转发 observer。

本文件负责：``retrieve()``、``extract_symbols()``、进程内 ``load()``。
A 层整次失败时降级为空列表并继续 B。
``coverage`` / ``recommended_action`` / ``escalate_suggested`` 只在这里算。

禁止：自己写 SQL、自己算 RRF、短路「A 命中就不查 B」。
调用方：``cache.retrieve_cached``、评测脚本、工具层。
被调用方：``tier_a.query_rules``、``tier_b.query_prose``、``observe``、``error_log``、
``config``（只读已 load 的对象）。

对应文档：``rag/retriever/docs/router-runtime.md``。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag.retriever.config import (
    RetrieverConfig,
    effective_k_a,
    effective_k_b,
    load_config,
)
from rag.retriever.error_log import write_tier_a_event
from rag.retriever.observe import (
    RetrieveStartEvent,
    RetrievalTraceEvent,
    TierAErrorEvent,
    get_observer,
    safe_observe,
)
from rag.retriever.rerank import get_reranker
from rag.retriever.schemas import (
    AgentAction,
    ProseHit,
    RetrievalMode,
    RetrievalQuery,
    RetrievalResult,
    StructuredHit,
    UnifiedHit,
)
from rag.retriever.tier_a import assert_schema_version, query_rules
from rag.retriever.tier_b import query_prose

_LOG = logging.getLogger("rag.retriever.router")
_RAG_ROOT = Path(__file__).resolve().parent.parent

_FN_RE = re.compile(r"Nonexistent function '([^']+)'")
_INDEX_RE = re.compile(r"Invalid get index '([^']+)'")
_IDENT_RE = re.compile(r'Identifier "([^"]+)" not found')
_BACKTICK_RE = re.compile(r"`([^`]+)`")


@dataclass
class RuntimeHandles:
    """进程内复用的库句柄。``load()`` 一次，后续检索共用。"""

    conn: sqlite3.Connection
    table: Any | None
    artifacts_dir: Path
    manifest_hash: str
    config: RetrieverConfig


_HANDLES: RuntimeHandles | None = None


def extract_symbols(error_text: str) -> list[str]:
    """从 Godot 报错原文用写死正则抠符号。失败返回空列表，不是异常。"""
    if not error_text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for pattern in (_FN_RE, _INDEX_RE, _IDENT_RE, _BACKTICK_RE):
        for match in pattern.finditer(error_text):
            token = match.group(1).strip()
            if token and token not in seen:
                seen.add(token)
                found.append(token)
    return found


def _default_artifacts_dir() -> Path:
    env = os.environ.get("RAG_ARTIFACTS")
    if env:
        return Path(env)
    return _RAG_ROOT / "artifacts"


def compute_manifest_hash(artifacts_dir: Path) -> str:
    """库指纹：lock 的 schema/files/row_count，并折进 B 层 corpora manifest。"""
    payload: dict[str, Any] = {}
    lock_path = artifacts_dir / "manifest.lock.json"
    if lock_path.is_file():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        payload["schema_version"] = lock.get("schema_version")
        payload["files"] = lock.get("files")
        payload["row_count"] = lock.get("row_count")
    corpora = artifacts_dir / "corpora" / "default" / "manifest.json"
    if corpora.is_file():
        payload["corpora_default"] = json.loads(corpora.read_text(encoding="utf-8"))
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _open_sqlite(path: Path, log_dir: str | None) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"找不到 A 层规则库: {path}")
    uri = path.resolve().as_uri()
    sep = "&" if "?" in uri else "?"
    conn = sqlite3.connect(f"{uri}{sep}mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    assert_schema_version(conn, log_dir=log_dir)
    return conn


def _open_lance_table(artifacts_dir: Path, strategy_id: str) -> Any | None:
    candidates = [
        artifacts_dir / "corpora" / strategy_id,
        artifacts_dir / "corpus.lance",
        artifacts_dir,
    ]
    try:
        import lancedb
    except ImportError:
        _LOG.warning("未安装 lancedb，B 层不可用")
        return None
    for uri in candidates:
        if not uri.exists():
            continue
        try:
            db = lancedb.connect(str(uri))
            try:
                names = list(db.list_tables().tables or [])
            except Exception:
                names = []
            if names and "corpus" not in names:
                continue
            return db.open_table("corpus")
        except Exception:
            _LOG.exception("打开 Lance 表失败: %s", uri)
            continue
    _LOG.warning("未找到 corpus 表（已试 corpora/%s 与 artifacts/）", strategy_id)
    return None


def load(
    *,
    artifacts_dir: Path | str | None = None,
    config_path: Path | str | None = None,
    strategy_id: str = "default",
) -> RuntimeHandles:
    """打开 SQLite + Lance + YAML，进程内只应调用一次。"""
    global _HANDLES
    cfg = load_config(Path(config_path) if config_path else None)
    art = Path(artifacts_dir) if artifacts_dir is not None else _default_artifacts_dir()
    conn = _open_sqlite(art / "rules.db", cfg.observability.log_dir)
    table = _open_lance_table(art, strategy_id)
    handles = RuntimeHandles(
        conn=conn,
        table=table,
        artifacts_dir=art,
        manifest_hash=compute_manifest_hash(art),
        config=cfg,
    )
    _HANDLES = handles
    return handles


def get_handles() -> RuntimeHandles:
    """返回已 ``load()`` 的句柄；尚未加载则按默认路径加载。"""
    if _HANDLES is None:
        return load()
    return _HANDLES


def set_handles(handles: RuntimeHandles | None) -> None:
    """测试注入 / 清空进程内句柄。"""
    global _HANDLES
    _HANDLES = handles


def _config_snapshot(config: RetrieverConfig) -> dict[str, Any]:
    return {
        "tier_a.top_k": config.tier_a.top_k,
        "channels": config.tier_b.channels,
        "bm25.k": config.tier_b.bm25.k,
        "vector.k": config.tier_b.vector.k,
        "recall_k": config.tier_b.recall_k,
        "rerank_k": config.tier_b.rerank_k,
        "score_threshold": config.tier_b.score_threshold,
        "reranker": config.tier_b.reranker,
        "rrf_k": config.tier_b.fusion.rrf_k,
    }


def _query_digest(query: RetrievalQuery) -> dict[str, Any]:
    error = query.error_text or ""
    if len(error) > 240:
        error = error[:240] + "…"
    return {
        "error_text": error,
        "symbols": list(query.symbols),
        "target_version": query.target_version,
        "retrieval_mode": query.retrieval_mode.value,
    }


def _match_a(rule: Any, symbols: list[str]) -> tuple[float, str]:
    symbol_set = set(symbols)
    if rule.old_symbol and rule.old_symbol in symbol_set:
        return 1.0, "old_symbol"
    if rule.new_symbol and rule.new_symbol in symbol_set:
        return 1.0, "new_symbol"
    if rule.owner and rule.owner in symbol_set:
        return 1.0, "owner"
    return 0.7, "match_tokens"


def _b_query_text(query: RetrievalQuery, symbols: list[str]) -> str:
    if query.error_text and query.error_text.strip():
        return query.error_text.strip()
    if query.query_text and query.query_text.strip():
        return query.query_text.strip()
    return " ".join(symbols)


def _coverage(structured: list[StructuredHit], prose: list[ProseHit]) -> str:
    if structured:
        return "rule_hit"
    if prose:
        return "prose_only"
    return "no_hit"


def retrieve(
    query: RetrievalQuery | Any,
    *,
    config: RetrieverConfig | None = None,
    observer: Any = None,
) -> RetrievalResult:
    """执行一次 A+B 检索。``cache_hit`` 恒为 False；命中由 ``retrieve_cached`` 改写。"""
    if not isinstance(query, RetrievalQuery):
        query = RetrievalQuery.model_validate(query)

    t0 = time.perf_counter()
    observer = observer if observer is not None else get_observer()
    handles = get_handles()
    cfg = config if config is not None else handles.config
    log_dir = cfg.observability.log_dir

    if query.file_hint:
        _LOG.debug("file_hint=%s（本协议不进 WHERE）", query.file_hint)

    safe_observe(
        observer,
        "on_retrieve_start",
        RetrieveStartEvent(
            request_id=query.request_id,
            config_snapshot=_config_snapshot(cfg),
        ),
    )

    symbols = list(query.symbols) if query.symbols else extract_symbols(query.error_text or "")
    limit_a = effective_k_a(query.top_k_a, cfg, query.top_k)
    limit_b = effective_k_b(query.top_k_b, cfg, query.top_k)
    tier_b = cfg.tier_b.model_copy(update={"rerank_k": limit_b})

    structured: list[StructuredHit] = []
    if query.retrieval_mode != RetrievalMode.semantic_only:
        try:
            rules = query_rules(
                handles.conn,
                symbols=symbols,
                target_version_code=query.target_version_code,
                kinds=query.kinds,
                limit=limit_a,
                request_id=query.request_id,
                observer=observer,
                log_dir=log_dir,
            )
            for rule in rules:
                score, reason = _match_a(rule, symbols)
                structured.append(StructuredHit(rule=rule, score=score, match_reason=reason))
        except Exception as exc:
            write_tier_a_event(
                event="query_failed",
                request_id=query.request_id,
                symbols=symbols,
                target_version_code=query.target_version_code,
                error_type=type(exc).__name__,
                error_message=str(exc),
                log_dir=log_dir,
            )
            safe_observe(
                observer,
                "on_tier_a_error",
                TierAErrorEvent(
                    event="query_failed",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    symbols=symbols,
                    target_version_code=query.target_version_code,
                    request_id=query.request_id,
                ),
            )
            structured = []

    prose: list[ProseHit] = []
    b_stats: dict[str, Any] = {
        "threshold_dropped": 0,
        "rerank_changed_top1": False,
        "channel_ranks": {},
    }
    if query.retrieval_mode != RetrievalMode.exact_only:
        b_text = _b_query_text(query, symbols)
        try:
            rerank_fn = get_reranker(tier_b.reranker)
            prose = query_prose(
                handles.table,
                text=b_text,
                target_version_code=query.target_version_code,
                config=tier_b,
                rerank_fn=rerank_fn,
                observer=observer,
                request_id=query.request_id,
                stats=b_stats,
            )
        except Exception:
            _LOG.exception("B 层检索失败，按空列表降级（已打日志，不当成静默 no_hit）")
            prose = []

    merged: list[UnifiedHit] = [
        UnifiedHit(layer="A", score=hit.score, structured=hit.rule) for hit in structured
    ] + [UnifiedHit(layer="B", score=hit.score, prose=hit.chunk) for hit in prose]

    coverage = _coverage(structured, prose)
    recommended: AgentAction | None = structured[0].rule.agent_action if structured else None
    escalate = coverage == "no_hit" or recommended == AgentAction.escalate_human
    took_ms = (time.perf_counter() - t0) * 1000.0

    result = RetrievalResult(
        resolved_symbols=symbols,
        target_version_code=query.target_version_code,
        structured_hits=structured,
        prose_hits=prose,
        merged=merged,
        coverage=coverage,  # type: ignore[arg-type]
        recommended_action=recommended,
        escalate_suggested=escalate,
        cache_hit=False,
        took_ms=took_ms,
    )

    safe_observe(
        observer,
        "on_retrieve_end",
        RetrievalTraceEvent(
            request_id=query.request_id,
            ts=datetime.now(timezone.utc).isoformat(),
            query_digest=_query_digest(query),
            config_snapshot=_config_snapshot(cfg),
            resolved_symbols=symbols,
            structured_hits=[
                {"id": h.rule.id, "score": h.score, "match_reason": h.match_reason}
                for h in structured
            ],
            prose_hits=[
                {"id": h.chunk.id, "score": h.score, "match_reason": h.match_reason}
                for h in prose
            ],
            coverage=coverage,
            recommended_action=recommended.value if recommended else None,
            escalate_suggested=escalate,
            cache_hit=False,
            took_ms=took_ms,
            threshold_dropped=int(b_stats.get("threshold_dropped") or 0),
            channel_ranks=dict(b_stats.get("channel_ranks") or {}),
            rerank_changed_top1=bool(b_stats.get("rerank_changed_top1")),
        ),
    )
    return result
