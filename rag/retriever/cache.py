"""检索结果缓存。门牌号，不是数据完整性校验。

本文件负责：``cache_key()``、``retrieve_cached()``。命中时只把 ``cache_hit``
改为 True，不得改 hits / coverage / recommended_action。

禁止：在这里打开 Lance、拼 SQL、把 ``request_id`` 编进 key、改命中结果的业务字段。
调用方：``__init__.retrieve_cached``（工具层）。
被调用方：``router.retrieve``（未命中时）。

对应文档：``rag/retriever/docs/router-runtime.md`` §5、
``docs/hash_and_manifest.md``。
"""

from __future__ import annotations

import hashlib
from typing import Any

from rag.retriever.config import RetrieverConfig, config_hash, load_config
from rag.retriever.router import get_handles, retrieve
from rag.retriever.schemas import RetrievalQuery, RetrievalResult

_STORE: dict[str, RetrievalResult] = {}


def cache_key(query: RetrievalQuery | Any, manifest_hash: str, config_hash_value: str) -> str:
    """``sha256(manifest_hash + ':' + config_hash + ':' + query_json)``。

    ``query_json`` 必须排除 ``request_id``。
    """
    if not isinstance(query, RetrievalQuery):
        query = RetrievalQuery.model_validate(query)
    payload = query.model_dump_json(exclude={"request_id"})
    blob = f"{manifest_hash}:{config_hash_value}:{payload}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def clear_cache() -> None:
    """测试 / 进程内清空结果缓存。"""
    _STORE.clear()


def retrieve_cached(
    query: RetrievalQuery | Any,
    *,
    config: RetrieverConfig | None = None,
    observer: Any = None,
) -> RetrievalResult:
    """先查缓存，未命中再 ``router.retrieve``。命中只改 ``cache_hit=True``。"""
    if not isinstance(query, RetrievalQuery):
        query = RetrievalQuery.model_validate(query)
    handles = get_handles()
    cfg = config if config is not None else handles.config
    if cfg is None:
        cfg = load_config()
    key = cache_key(query, handles.manifest_hash, config_hash(cfg))
    hit = _STORE.get(key)
    if hit is not None:
        return hit.model_copy(update={"cache_hit": True})
    result = retrieve(query, config=cfg, observer=observer)
    _STORE[key] = result
    return result
