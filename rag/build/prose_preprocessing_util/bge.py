"""兼容转发：真正的 TextEmbedding 单例在 ``rag.bge``。

build 切块/建库与 retriever ``query_embed`` 必须共用同一进程内模型，
禁止在 Lance 表上再挂另一套 embedding function。
"""

from __future__ import annotations

from rag.bge import EMBEDDING_MODEL, bge_token_count, get_text_embedding

__all__ = ["EMBEDDING_MODEL", "bge_token_count", "get_text_embedding"]
