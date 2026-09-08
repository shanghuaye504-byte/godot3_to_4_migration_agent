"""`RetryGateConfig` + `load_retry_gate_config` 的纯函数测试。

覆盖要点：
- 默认值与方案文档 §4.1 一致
- YAML 覆盖默认值生效（含嵌套 `retry_gate:` 与扁平映射两种写法）
- 未知字段报 ValueError，防止拼错被默默忽略
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from godot_mcp.verify_gate.config import RetryGateConfig, load_retry_gate_config


def test_defaults_match_scheme() -> None:
    cfg = RetryGateConfig()
    assert cfg.no_progress_window == 3
    assert cfg.oscillation_window == 3
    assert cfg.file_stuck_threshold == 3
    assert cfg.infra_failure_streak_limit == 3
    assert cfg.rounds_limit == 40
    assert cfg.cost_limit_usd == 5.0


def test_load_without_path_returns_defaults() -> None:
    assert load_retry_gate_config() == RetryGateConfig()


def test_yaml_nested_overrides(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(
        yaml.safe_dump({"retry_gate": {"rounds_limit": 10, "cost_limit_usd": 1.5}}),
        encoding="utf-8",
    )
    cfg = load_retry_gate_config(path)
    assert cfg.rounds_limit == 10
    assert cfg.cost_limit_usd == 1.5
    assert cfg.no_progress_window == 3


def test_yaml_flat_overrides(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(yaml.safe_dump({"file_stuck_threshold": 7}), encoding="utf-8")
    cfg = load_retry_gate_config(path)
    assert cfg.file_stuck_threshold == 7


def test_unknown_field_raises(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(
        yaml.safe_dump({"retry_gate": {"no_progress_widow": 3}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown retry_gate fields"):
        load_retry_gate_config(path)
