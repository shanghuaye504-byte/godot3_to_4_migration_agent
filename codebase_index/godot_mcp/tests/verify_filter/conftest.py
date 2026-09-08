"""共享测试辅助：从 `fixtures/godot_4_7_1/` 读取黄金原文样例。"""

from __future__ import annotations

from pathlib import Path

import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "godot_4_7_1"


@pytest.fixture
def load_fixture():
    """返回一个函数：`load_fixture("sample_a_autoload_fp_cold.log")` -> 文件内容字符串。"""

    def _load(name: str) -> str:
        return (_FIXTURES_DIR / name).read_text(encoding="utf-8")

    return _load
