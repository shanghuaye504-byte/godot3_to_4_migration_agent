"""对外入口。

本文件负责：re-export ``retrieve`` / ``retrieve_cached`` / ``load``，以及 schema
符号。Agent 工具只应 import 本模块。

禁止：在这里写 SQL、打开 ``rules.db`` / Lance、读取 YAML 逻辑。
调用方：LangGraph 工具函数、eval 脚本。
被调用方：``cache.retrieve_cached``、``router.retrieve``。

对应文档：``rag/retriever/README.md``、``rag/retriever/ARCHITECTURE.md``。
"""

from __future__ import annotations

from rag.retriever.cache import retrieve_cached
from rag.retriever.config import RetrieverConfig, config_hash, load_config
from rag.retriever.observe import (
    CompositeObserver,
    NoOpObserver,
    get_observer,
    set_observer,
)
from rag.retriever.router import extract_symbols, get_handles, load, retrieve, set_handles
from rag.retriever.schemas import (
    AGENT_VISIBLE_DETECTION_METHODS,
    SKIP_DETECTION_METHODS,
    AgentAction,
    ChangeKind,
    DetectionMethod,
    MigrationRule,
    ProseChunk,
    ProseHit,
    RetrievalMode,
    RetrievalQuery,
    RetrievalResult,
    StructuredHit,
    SymbolKind,
    UnifiedHit,
)

__all__ = [
    "AGENT_VISIBLE_DETECTION_METHODS",
    "SKIP_DETECTION_METHODS",
    "AgentAction",
    "ChangeKind",
    "CompositeObserver",
    "DetectionMethod",
    "MigrationRule",
    "NoOpObserver",
    "ProseChunk",
    "ProseHit",
    "RetrievalMode",
    "RetrievalQuery",
    "RetrievalResult",
    "RetrieverConfig",
    "StructuredHit",
    "SymbolKind",
    "UnifiedHit",
    "config_hash",
    "extract_symbols",
    "get_handles",
    "get_observer",
    "load",
    "load_config",
    "retrieve",
    "retrieve_cached",
    "set_handles",
    "set_observer",
]
