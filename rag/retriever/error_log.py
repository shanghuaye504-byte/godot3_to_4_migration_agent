"""A 层失败落盘。不要命名为 logging.py，以免覆盖标准库。

本文件负责：把 schema 不匹配、整次查询失败、单行校验失败写成 JSONL。
目录来自 YAML ``observability.log_dir``，默认 ``artifacts/logs/retriever/``。

禁止：被 ``tier_b`` / ``rerank`` 调用、在这里做检索、受 ``sample_rate`` 丢弃事故行。
调用方：``tier_a.query_rules``（单行）、开库处（schema_version）、``router``（整次失败）。
被调用方：无。

对应文档：``rag/retriever/docs/tier-a.md`` §6。
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

_LOG = logging.getLogger("rag.retriever.error_log")
_RAG_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_REL = Path("artifacts/logs/retriever")
_LOCK = threading.Lock()
_schema_drift_total = 0


def _resolve_log_dir(log_dir: str | None) -> Path:
    raw = Path(log_dir) if log_dir else _DEFAULT_REL
    if not raw.is_absolute():
        raw = _RAG_ROOT / raw
    return raw


def write_tier_a_event(
    *,
    event: str,
    level: str = "error",
    request_id: str | None = None,
    symbols: list[str] | None = None,
    target_version_code: int | None = None,
    rule_id: str | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    row_excerpt: str | None = None,
    log_dir: str | None = None,
) -> None:
    """追加一行 JSONL，并同步打 Python logging。

    写盘失败只记 ``logging.exception``，不得打断「skip 该行」的控制流。
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event": event,
        "request_id": request_id,
        "symbols": symbols,
        "target_version_code": target_version_code,
        "rule_id": rule_id,
        "error_type": error_type,
        "error_message": error_message,
        "row_excerpt": row_excerpt,
    }
    log_fn = _LOG.error if level == "error" else _LOG.warning
    log_fn("tier_a %s: %s", event, error_message or error_type or "")
    try:
        dest_dir = _resolve_log_dir(log_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "tier_a.jsonl"
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with _LOCK:
            with dest.open("a", encoding="utf-8") as fh:
                fh.write(line)
    except Exception:
        _LOG.exception("写入 A 层错误 JSONL 失败")


def increment_schema_drift() -> None:
    """``rules_schema_drift_total`` 风格计数器 +1。"""
    global _schema_drift_total
    _schema_drift_total += 1


def schema_drift_total() -> int:
    """当前进程内 schema drift 计数，给测试和以后的 Prom 用。"""
    return _schema_drift_total


def reset_schema_drift() -> None:
    """测试用。"""
    global _schema_drift_total
    _schema_drift_total = 0
