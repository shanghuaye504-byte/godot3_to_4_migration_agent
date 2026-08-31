"""rag 包的 pytest 启动垫片。

``rag/pyproject.toml`` 里 ``testpaths = ["test"]``。``eval/`` 只放离线召回评测，
不进默认套件。这里的测试需要两个 import 根：

* ``rag.*`` — 可编辑安装的包（``uv sync``）。
* ``prose_preprocessing_util`` — 只存在于 ``rag/build/`` 的编译辅助包，
  不进 wheel。和 process 脚本一样，把 ``rag/build`` 放进 ``sys.path``。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
if str(BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(BUILD_DIR))


@pytest.fixture(autouse=True)
def _reset_retriever_runtime() -> None:
    """每个用例后清掉 retriever 进程态，避免缓存 / observer / 句柄串味。"""
    from rag.retriever.cache import clear_cache
    from rag.retriever.config import clear_config_cache
    from rag.retriever.error_log import reset_schema_drift
    from rag.retriever.observe import NoOpObserver, set_observer
    from rag.retriever.router import set_handles
    from rag.retriever.tier_b import reset_fts_cache

    set_handles(None)
    clear_cache()
    clear_config_cache()
    reset_schema_drift()
    reset_fts_cache()
    set_observer(NoOpObserver())
    yield
    set_handles(None)
    clear_cache()
    clear_config_cache()
    reset_schema_drift()
    reset_fts_cache()
    set_observer(NoOpObserver())
