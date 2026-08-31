"""运行时 BGE 单例：建库 ``passage_embed`` 与检索 ``query_embed`` 共用同一模型。

必须放在包根（和 ``version_codec.py`` 一样），worker 镜像不带 ``rag/build/``。
``prose_preprocessing_util.bge`` 从此处再导出，避免两套单例。
"""

from __future__ import annotations

from typing import Any

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384

_model: Any = None
_model_name: str | None = None


def get_text_embedding(model_name: str | None = None) -> Any:
    """懒加载 ``TextEmbedding``。缓存目录读 ``FASTEMBED_CACHE_PATH``。"""
    global _model, _model_name
    name = model_name or EMBEDDING_MODEL
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:
        raise RuntimeError(
            "fastembed 是检索 query_embed / 建库 passage_embed 的运行时依赖。"
            "请在 rag/ 下执行: uv sync --group build --group dev"
        ) from exc
    if _model is None or _model_name != name:
        _model = TextEmbedding(model_name=name)
        _model_name = name
    return _model


def bge_token_count(text: str) -> int:
    """用 bge-small 的 WordPiece 数 token。空串返回 0。"""
    if not text or not str(text).strip():
        return 0
    raw = get_text_embedding().token_count(text)
    if isinstance(raw, int):
        n = raw
    elif isinstance(raw, float):
        n = int(raw)
    else:
        n = int(sum(int(x) for x in raw))
    return max(1, n)
