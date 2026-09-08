"""MCP server 封装测试：不跑 stdio、不拉 Godot。

覆盖要点：
- 工具列表恰好一个 `verify`
- 配置缺失 → ToolError，不裸抛 Traceback
- 调用 verify 能拿到结构化 JSON 字典
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from godot_mcp.config import Config
from godot_mcp.server import create_server
from godot_mcp.verify_gate.config import RetryGateConfig
from godot_mcp.verify_gate.models import VerifyGateResult
from godot_mcp.verify_gate.state_store import InMemoryStateStore
from godot_mcp.verify_gate.tool import run_verify_tool
from mcp.server.mcpserver.exceptions import ToolError

from tests.test_verify_tool import _load, _ok


def test_lists_only_verify() -> None:
    server = create_server(load_config_fn=lambda: Config(project_root=Path("/tmp"), godot_binary="godot4"))
    tools = asyncio.run(server.list_tools())
    assert [tool.name for tool in tools] == ["verify"]
    dumped = tools[0].model_dump(by_alias=True)
    schema = dumped.get("inputSchema") or dumped.get("input_schema") or {}
    props = schema.get("properties") or {}
    for banned in ("unified_diff", "phase", "patched_files"):
        assert banned not in props


def test_missing_config_is_tool_error() -> None:
    def boom() -> Config:
        raise FileNotFoundError("/no/such/config.yaml")

    server = create_server(load_config_fn=boom)

    with pytest.raises(ToolError, match="配置未就绪"):
        asyncio.run(server.call_tool("verify", {"kind": "check_workspace"}))


def test_missing_project_root_field_is_tool_error() -> None:
    def boom() -> Config:
        raise KeyError("project_root")

    server = create_server(load_config_fn=boom)

    with pytest.raises(ToolError, match="project_root"):
        asyncio.run(server.call_tool("verify", {"kind": "check_workspace"}))


def test_call_verify_returns_structured_dict(tmp_path: Path) -> None:
    stderr = _load("sample_e_real_syntax_error.log")
    config = Config(project_root=tmp_path, godot_binary="godot4")
    store = InMemoryStateStore()

    def verify_fn(kind: str, target: str | None, **kwargs: object) -> VerifyGateResult:
        return run_verify_tool(
            kind,
            target,
            session_id=str(kwargs.get("session_id") or "default"),
            config=config,
            gate_cfg=RetryGateConfig(),
            state_store=store,
            run_verify_fn=lambda *_a: _ok("V2", stderr),
        )

    server = create_server(
        load_config_fn=lambda: config,
        verify_fn=verify_fn,
        state_store=store,
    )
    result = asyncio.run(
        server.call_tool(
            "verify",
            {"kind": "check_file", "target": "res://orphan_bad_parse.gd"},
        )
    )
    assert result.is_error is not True
    payload = result.structured_content or {}
    if not payload and result.content:
        # 兜底：有的 SDK 版本只把 dict 放进 text content
        import json

        payload = json.loads(result.content[0].text)  # type: ignore[index]
    assert payload["project_status"] == "HAS_ERRORS"
    assert payload["decision"] == "CONTINUE"
    assert payload["hard_stop"] is False
    assert payload["root_cause_errors"]
    assert "probe_incomplete" in payload
    assert "gdscript_complete" in payload


def test_unknown_removed_fields_are_rejected_or_ignored(tmp_path: Path) -> None:
    config = Config(project_root=tmp_path, godot_binary="godot4")
    stderr = _load("sample_e_real_syntax_error.log")
    store = InMemoryStateStore()

    def verify_fn(kind: str, target: str | None, **kwargs: object) -> VerifyGateResult:
        return run_verify_tool(
            kind,
            target,
            session_id="default",
            config=config,
            gate_cfg=RetryGateConfig(),
            state_store=store,
            run_verify_fn=lambda *_a: _ok("V2", stderr),
        )

    server = create_server(load_config_fn=lambda: config, verify_fn=verify_fn, state_store=store)
    result = asyncio.run(
        server.call_tool(
            "verify",
            {
                "kind": "check_file",
                "target": "res://orphan_bad_parse.gd",
                "unified_diff": "should-be-ignored",
            },
        )
    )
    assert result.is_error is not True
