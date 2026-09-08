"""MCP server 入口：仅注册 verify 工具。

范围降级说明：原规划包含 hover_symbol / workspace_symbol / verify 三个工具。
由于 LSP 会引入不可预测的进程/端口冲突，且时间紧张，现决定完全去掉 LSP 方案。
本 server 只暴露 verify(kind, target?) 一个工具。

verify 内部是 godot_mcp.verify_gate.run_verify_tool 的薄封装：先用
verify_filter 把 Godot 原始输出过滤/合并成 ProjectFilterView，再用
verify_gate.algorithm.evaluate 判定这一轮相对历史处于什么状态（继续/无进展/
单文件卡住/震荡/预算耗尽/基础设施熔断）。对 LLM 而言，返回值是 VerifyGateResult
的 JSON 字典（过滤结果 + Gate 判定），hard_stop=True 时宿主 Agent 循环会在这次
工具调用返回之后强制结束会话。

启动方式：godot-mcp 命令或 python -m godot_mcp.server（stdio 传输），
由 Agent 的 MCP 客户端配置指向本入口。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from godot_mcp.config import Config, load_config
from godot_mcp.verify_gate.state_store import InMemoryStateStore, StateStore
from godot_mcp.verify_gate.tool import gate_result_to_dict, run_verify_tool


def create_server(
    *,
    load_config_fn: Callable[[], Config] | None = None,
    verify_fn: Callable[..., Any] | None = None,
    state_store: StateStore | None = None,
) -> MCPServer:
    """构建只注册 `verify` 的 MCP server。依赖可注入，方便单元测试。

    启动时不读 config.yaml——配置缺失应在工具调用时以 ToolError 返回，
    而不是让进程在启动瞬间崩溃。
    """
    server = MCPServer(
        name="godot-mcp",
        version="0.1.0",
        instructions="Godot 3→4 迁移校验：只暴露 verify 一个工具。",
    )
    store = state_store or InMemoryStateStore()
    load_cfg = load_config_fn or load_config
    run_tool = verify_fn or run_verify_tool

    @server.tool(
        name="verify",
        description=(
            "对当前 Godot 项目跑一次 headless 校验。"
            "kind 只能是 check_file 或 check_workspace；"
            "check_file 必须给 target。"
            "check_workspace 会走外壳：条件 V3、V1↔V2 收敛、收尾门。"
            "phase / unified_diff / patched_files 由工具内部从会话状态与工作区快照组装，不必传入。"
        ),
    )
    def verify(
        kind: Literal["check_file", "check_workspace"],
        target: str | None = None,
        session_id: str = "default",
        workspace_id: str | None = None,
        round_cost_usd: float = 0.0,
    ) -> dict[str, Any]:
        try:
            config = load_cfg()
        except FileNotFoundError as exc:
            raise ToolError(f"配置未就绪：找不到 config.yaml（{exc}）") from exc
        except KeyError as exc:
            raise ToolError(f"配置未就绪：缺少字段 {exc}") from exc

        try:
            result = run_tool(
                kind,
                target,
                session_id=session_id,
                workspace_id=workspace_id,
                round_cost_usd=round_cost_usd,
                config=config,
                state_store=store,
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

        return gate_result_to_dict(result)

    return server


def main() -> None:
    """构建 MCP server、注册 verify 工具、跑 stdio 传输循环。"""
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
