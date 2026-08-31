"""可插拔重排。对 retriever 透明：只认 chunk 列表 → 分数。

本文件负责：``RerankFn`` 协议、``identity_rerank``、``minilm_l6_rerank``，
以及按 YAML 名字取出 callable 的 ``get_reranker()``。

禁止：碰 Lance / SQLite、在本模块展开某种模型的超参到 YAML、import ``router``。
调用方：``tier_b.query_prose``（排序 + 截 rerank_k 在 tier_b，不在这里截）。
被调用方：无。

对应文档：``rag/retriever/docs/tier-b.md``（§3.4）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol

# 模型名闭包在本文件，不进 YAML。换模型 = 换注册名或换这个常量。
MINILM_L6_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
_MINILM_BATCH = 32

_cross_encoder: Any = None
_cross_encoder_name: str | None = None


class RerankFn(Protocol):
    """``(query_text, candidates) -> 与 candidates 等长的分数``，越高越相关。"""

    def __call__(self, query_text: str, chunks: Sequence[Any]) -> Sequence[float]: ...


def identity_rerank(query_text: str, chunks: Sequence[Any]) -> Sequence[float]:
    """默认重排：不改变融合顺序。

    返回全 0，配合稳定排序保持 RRF 顺序。``query_text`` 对 identity 无意义。
    """
    del query_text
    return [0.0] * len(chunks)


def _chunk_passage(chunk: Any) -> str:
    """送给 cross-encoder 的文本：heading 路径 + body，与建库 embedding_text 同形。"""
    heading = getattr(chunk, "heading_path", None) or []
    body = getattr(chunk, "text", None)
    if body is None:
        body = ""
    body = str(body)
    if heading:
        prefix = " > ".join(str(part) for part in heading)
        return f"{prefix}\n\n{body}" if body else prefix
    return body if body else str(chunk)


def _get_cross_encoder(model_name: str = MINILM_L6_MODEL) -> Any:
    """懒加载 ``TextCrossEncoder``。缓存目录读 ``FASTEMBED_CACHE_PATH``。"""
    global _cross_encoder, _cross_encoder_name
    if _cross_encoder is not None and _cross_encoder_name == model_name:
        return _cross_encoder
    try:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
    except ImportError as exc:
        raise RuntimeError(
            "fastembed 是 minilm_l6 重排的运行时依赖。"
            "请在 rag/ 下执行: uv sync --group build --group dev"
        ) from exc
    _cross_encoder = TextCrossEncoder(model_name=model_name)
    _cross_encoder_name = model_name
    return _cross_encoder


def minilm_l6_rerank(query_text: str, chunks: Sequence[Any]) -> Sequence[float]:
    """``Xenova/ms-marco-MiniLM-L-6-v2``：fastembed ONNX cross-encoder，约 80MB。

    粗召回已经够准时用这个，不换 1GB 级 BGE reranker。
    """
    if not chunks:
        return []
    documents = [_chunk_passage(chunk) for chunk in chunks]
    scores = _get_cross_encoder().rerank(
        query_text or "",
        documents,
        batch_size=_MINILM_BATCH,
    )
    return [float(score) for score in scores]


def reset_cross_encoder() -> None:
    """测试用：丢掉进程内单例，下次调用重新加载。"""
    global _cross_encoder, _cross_encoder_name
    _cross_encoder = None
    _cross_encoder_name = None


_REGISTRY: dict[str, Callable[[str, Sequence[Any]], Sequence[float]]] = {
    "identity": identity_rerank,
    "minilm_l6": minilm_l6_rerank,
}


def get_reranker(name: str) -> Callable[[str, Sequence[Any]], Sequence[float]]:
    """把 YAML ``tier_b.reranker`` 注册名映射为 callable。未知名报 ``KeyError``。"""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"未注册的 reranker: {name}") from exc


def register_reranker(
    name: str, fn: Callable[[str, Sequence[Any]], Sequence[float]]
) -> None:
    """评测或实验注册额外重排。超参必须闭包在 ``fn`` 内。"""
    _REGISTRY[name] = fn
