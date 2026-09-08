"""verify_gate —— 独立于噪声过滤器与 LLM 之外的、确定性的、有状态的重试判定层。

完整规格见 `../../../docs/verifier_retry_gate_scheme.md`（下称"方案文档"）。与
`verify_filter/`（无状态纯函数）不同，本包**有状态**：它要回答的问题天生是跨轮次的
（"和上一轮比怎么样""过去 3 轮怎么样"），状态读写接口见 `state_store.py`。

```text
Godot 子进程（有副作用，慢）
  ↓ 原始 stdout/stderr
噪声过滤器（verify_filter/，纯函数，无状态）
  ↓ FilterResult / ProjectFilterView
Verify Gate（本包，有状态，确定性代码，非 LLM）
  ↓ VerifyGateResult
Agent 循环 / LLM（只在 Gate 允许的范围内做决策；硬停止 LLM 无法绕过）
```

粒度契约（方案文档 §2.2.4，与 `verify_filter` §2.1/§7.10 的收敛循环衔接）：**一次
`evaluate()` 调用 = 一次外部 `run_verify` 工具调用 = 一个 Agent round**。`verify_filter`
内部的 V1↔V2 收敛循环、收尾门 V3，必须在调用 `evaluate()` 之前全部跑完；本包不感知、
也不需要感知内部子循环跑了几轮。

落地路径说明（方案文档 §7"落地路径"）：当前阶段落在
`codebase_index/godot_mcp/src/godot_mcp/verify_gate/`，与 `verify_filter/` 是
`src/godot_mcp/` 下的兄弟包，只依赖 `verify_filter` 导出的 `FilterResult`/
`ProjectFilterView` 类型，不依赖其内部规则模块。若未来迁移 Agent 主体拆成独立顶层
包，本包可整目录搬迁，调用方只改 import 路径。

对外只暴露一个入口：`run_verify_tool`（组合过滤器 + Gate，对 LLM/MCP 暴露）。
"""

from __future__ import annotations

from godot_mcp.verify_gate.algorithm import evaluate
from godot_mcp.verify_gate.tool import gate_result_to_dict, run_verify_tool

__all__ = ["evaluate", "gate_result_to_dict", "run_verify_tool"]
