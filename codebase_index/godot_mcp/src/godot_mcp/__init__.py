"""godot_mcp —— Layer 3：自建 Godot MCP server（Python 实现）。

本包仅暴露一个 MCP 工具 `verify`，用于在 Agent 修改后拿到 Godot 4.x 的客观
解析/编译信号。

> **范围降级说明**：原规划包含常驻 LSP 会话 + 一次性校验子进程两类 Godot 子进程。
> 由于 LSP 会引入不可预测的进程/端口冲突，且时间紧张，现决定**完全去掉 LSP 方案**。
> 引擎语义查询统一由 Layer 2 的 `codeindex` CLI 承担。
"""
