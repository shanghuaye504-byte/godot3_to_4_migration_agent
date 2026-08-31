"""读取同目录 ``retriever.yaml``，产出运行时配置与缓存指纹。

本文件负责：``load_config()``、``RetrieverConfig``、``config_hash()``。
只读 YAML，不做检索。

禁止：查 SQLite / Lance、计算 RRF、写 JSONL、import ``rag.build``。
调用方：进程启动（一次）、``router.retrieve``、eval 的 ``run_ablation.py``。
被调用方：无（不要回调 tier_a / tier_b）。

对应文档：``rag/retriever/docs/config.md``。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

DEFAULT_YAML_PATH = Path(__file__).resolve().parent / "retriever.yaml"

_K_MIN = 1
_K_MAX = 50

_config_cache: dict[Path, Any] = {}


def _check_k(value: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} 必须是整数")
    if not _K_MIN <= value <= _K_MAX:
        raise ValueError(f"{name} 必须在 {_K_MIN}～{_K_MAX}")
    return value


class ChannelKConfig(BaseModel):
    """BM25 或向量一路的 k 与 RRF 权重。"""

    k: int = 3
    weight: float = 1.0

    @field_validator("k")
    @classmethod
    def _k(cls, value: int) -> int:
        return _check_k(value, "k")

    @field_validator("weight")
    @classmethod
    def _weight(cls, value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("weight 必须是数字")
        if value < 0:
            raise ValueError("weight 不能为负")
        return float(value)


class FusionConfig(BaseModel):
    method: Literal["rrf"] = "rrf"
    rrf_k: int = 60

    @field_validator("method")
    @classmethod
    def _method(cls, value: str) -> str:
        if value != "rrf":
            raise ValueError("fusion.method 目前只允许 rrf")
        return value

    @field_validator("rrf_k")
    @classmethod
    def _rrf_k(cls, value: int) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("fusion.rrf_k 必须是正整数")
        return value


class TierAConfig(BaseModel):
    top_k: int = 8

    @field_validator("top_k")
    @classmethod
    def _top_k(cls, value: int) -> int:
        return _check_k(value, "tier_a.top_k")


class TierBConfig(BaseModel):
    channels: Literal["hybrid", "bm25", "vector"] = "hybrid"
    bm25: ChannelKConfig = Field(default_factory=lambda: ChannelKConfig(k=3, weight=1.0))
    vector: ChannelKConfig = Field(default_factory=lambda: ChannelKConfig(k=10, weight=1.0))
    fusion: FusionConfig = Field(default_factory=FusionConfig)
    recall_k: int = 10
    rerank_k: int = 3
    score_threshold: float | None = None
    reranker: str = "identity"

    @field_validator("channels")
    @classmethod
    def _channels(cls, value: str) -> str:
        allowed = {"hybrid", "bm25", "vector"}
        if value not in allowed:
            raise ValueError("tier_b.channels 必须是 hybrid / bm25 / vector")
        return value

    @field_validator("recall_k", "rerank_k")
    @classmethod
    def _ks(cls, value: int) -> int:
        return _check_k(value, "recall_k/rerank_k")

    @field_validator("score_threshold")
    @classmethod
    def _threshold(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("score_threshold 必须是 null 或 [0, 1] 内的数字")
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError("score_threshold 必须在 [0, 1]")
        return float(value)

    @model_validator(mode="after")
    def _reranker_registered(self) -> TierBConfig:
        from rag.retriever.rerank import get_reranker

        try:
            get_reranker(self.reranker)
        except KeyError as exc:
            raise ValueError(f"reranker 未注册: {self.reranker}") from exc
        return self


class ObservabilityConfig(BaseModel):
    log_dir: str = "artifacts/logs/retriever"
    sample_rate: float = 0.0

    @field_validator("sample_rate")
    @classmethod
    def _rate(cls, value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("sample_rate 必须是数字")
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError("sample_rate 必须在 [0, 1]")
        return float(value)


class RetrieverConfig(BaseModel):
    """YAML 载入后的配置对象。非法值在 ``load_config`` 失败，不默默夹紧。"""

    tier_a: TierAConfig = Field(default_factory=TierAConfig)
    tier_b: TierBConfig = Field(default_factory=TierBConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)


def clear_config_cache() -> None:
    """测试用：丢掉进程内 YAML 缓存。"""
    _config_cache.clear()


def load_config(path: Path | None = None) -> RetrieverConfig:
    """读取 YAML 并校验。

    Args:
        path: 配置文件。``None`` 表示本包内与脚本同目录的 ``retriever.yaml``。

    Returns:
        校验通过的 ``RetrieverConfig``。同一路径进程内缓存。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: k 越界、权重为负、``channels`` 非法、阈值不在 [0,1] 等。
    """
    yaml_path = Path(path) if path is not None else DEFAULT_YAML_PATH
    yaml_path = yaml_path.resolve()
    cached = _config_cache.get(yaml_path)
    if cached is not None:
        return cached
    if not yaml_path.is_file():
        raise FileNotFoundError(f"找不到 retriever 配置: {yaml_path}")
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "pyyaml 是 retriever 运行时依赖，用来读 retriever.yaml。"
            "请在 rag/ 下 uv sync。"
        ) from exc
    raw: Any = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("retriever.yaml 顶层必须是 mapping")
    try:
        config = RetrieverConfig.model_validate(raw)
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    _config_cache[yaml_path] = config
    return config


def config_hash(config: RetrieverConfig) -> str:
    """对影响召回的键做稳定序列化再哈希，供 ``cache_key`` 使用。

    包含：A/B 的 k、两路权重、channels、fusion、recall_k、rerank_k、
    score_threshold、reranker 名。不含 ``request_id``、``log_dir``、
    ``sample_rate``。
    """
    payload = {
        "tier_a": {"top_k": config.tier_a.top_k},
        "tier_b": {
            "channels": config.tier_b.channels,
            "bm25": {"k": config.tier_b.bm25.k, "weight": config.tier_b.bm25.weight},
            "vector": {"k": config.tier_b.vector.k, "weight": config.tier_b.vector.weight},
            "fusion": {
                "method": config.tier_b.fusion.method,
                "rrf_k": config.tier_b.fusion.rrf_k,
            },
            "recall_k": config.tier_b.recall_k,
            "rerank_k": config.tier_b.rerank_k,
            "score_threshold": config.tier_b.score_threshold,
            "reranker": config.tier_b.reranker,
        },
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def effective_k_a(query_top_k_a: int | None, config: RetrieverConfig, query_top_k: int) -> int:
    """A 层 SQL LIMIT：``top_k_a`` > YAML ``tier_a.top_k`` > 契约 ``top_k``。"""
    if query_top_k_a is not None:
        return query_top_k_a
    if config.tier_a.top_k:
        return config.tier_a.top_k
    return query_top_k


def effective_k_b(query_top_k_b: int | None, config: RetrieverConfig, query_top_k: int) -> int:
    """B 层最终条数：``top_k_b`` > YAML ``rerank_k`` > 契约 ``top_k``。"""
    if query_top_k_b is not None:
        return query_top_k_b
    if config.tier_b.rerank_k:
        return config.tier_b.rerank_k
    return query_top_k
