"""对着成品 artifacts 做一次 A 层冒烟（不加载 BGE）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from rag.retriever.config import load_config
from rag.retriever.router import load, retrieve, set_handles
from rag.retriever.schemas import RetrievalMode, RetrievalQuery

_RAG = Path(__file__).resolve().parent.parent
_RULES = _RAG / "artifacts" / "rules.db"


@pytest.mark.skipif(not _RULES.is_file(), reason="缺少 artifacts/rules.db")
def test_smoke_exact_only_instance() -> None:
    set_handles(None)
    load(artifacts_dir=_RAG / "artifacts")
    result = retrieve(
        RetrievalQuery(
            error_text=(
                "Invalid call. Nonexistent function 'instance' in base 'PackedScene'."
            ),
            symbols=["instance"],
            target_version="4.7.1",
            retrieval_mode=RetrievalMode.exact_only,
        )
    )
    assert result.coverage == "rule_hit"
    assert result.resolved_symbols == ["instance"]
    news = {h.rule.new_symbol for h in result.structured_hits}
    assert "instantiate" in news
    assert result.merged[0].layer == "A"
    assert result.took_ms >= 0


def test_load_config_and_query_model() -> None:
    cfg = load_config()
    q = RetrievalQuery(symbols=["instance"], target_version="4.7.1")
    assert q.target_version_code == 40701
    assert cfg.tier_a.top_k == 8
