"""verify_gate 测试共享 fixture。"""

from __future__ import annotations

import pytest

from godot_mcp.verify_gate.config import RetryGateConfig


@pytest.fixture
def default_cfg() -> RetryGateConfig:
    return RetryGateConfig()
