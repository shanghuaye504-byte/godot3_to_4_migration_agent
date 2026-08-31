"""RetrieverConfig：YAML 校验、优先级、config_hash。"""

from __future__ import annotations

from pathlib import Path

import pytest

from rag.retriever.config import RetrieverConfig, config_hash, load_config


def test_load_default_yaml() -> None:
    cfg = load_config()
    assert cfg.tier_a.top_k == 8
    assert cfg.tier_b.channels == "hybrid"
    assert cfg.tier_b.bm25.k == 3
    assert cfg.tier_b.vector.k == 10
    assert cfg.tier_b.recall_k == 10
    assert cfg.tier_b.rerank_k == 3
    assert cfg.tier_b.score_threshold is None
    assert cfg.tier_b.reranker == "identity"
    assert cfg.tier_b.fusion.rrf_k == 60
    assert cfg.observability.sample_rate == 0.0


def test_config_hash_stable_and_ignores_observability() -> None:
    a = load_config()
    b = a.model_copy(deep=True)
    b.observability.sample_rate = 0.5
    b.observability.log_dir = "/tmp/other"
    assert config_hash(a) == config_hash(b)
    c = a.model_copy(deep=True)
    c.tier_b.vector.weight = 2.0
    assert config_hash(a) != config_hash(c)


def test_illegal_channels(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("tier_b:\n  channels: keyword\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)


def test_negative_weight(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("tier_b:\n  bm25:\n    k: 3\n    weight: -1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)


def test_unknown_reranker(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("tier_b:\n  reranker: cross-encoder-v0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="reranker"):
        load_config(path)


def test_minilm_l6_reranker_name_is_registered(tmp_path: Path) -> None:
    path = tmp_path / "ok.yaml"
    path.write_text("tier_b:\n  reranker: minilm_l6\n", encoding="utf-8")
    cfg = load_config(path)
    assert cfg.tier_b.reranker == "minilm_l6"


def test_k_out_of_range(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("tier_a:\n  top_k: 0\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)


def test_threshold_out_of_range(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("tier_b:\n  score_threshold: 1.5\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_empty_construct() -> None:
    cfg = RetrieverConfig()
    assert cfg.tier_b.vector.k == 10
