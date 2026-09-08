"""verify_filter —— 把 Godot 原始 stdout/stderr 变成可信结构化错误的纯函数包。

完整规格见 `../../../docs/verifier_filter_scheme.md`（下称"方案文档"）。本包整体是
**纯函数、无状态、无 IO、不起 Godot 子进程**：谁来跑 Godot、谁来决定要不要再跑一次
`--editor --import`，都是"外壳"（runner）的职责，不在这里实现（方案文档 §1 / §12）。

落地路径说明（方案文档 §13"落地路径"）：当前阶段本包就是这份规格的具体实现，物理
落在 `codebase_index/godot_mcp/src/godot_mcp/verify_filter/`；若未来迁移 Agent 主体
拆成独立顶层包，本包可以整目录搬迁，调用方只改 import 路径，下面重导出的函数签名
与字段契约不变。

对外只暴露三个入口，内部模块（`parse.py`/`signature.py`/`pipeline.py`/`rules/*`）都是
实现细节，不应被外部直接 import：

- `filter_verify_output`  —— 单次命令（V1/V2/V3/V5 之一）的过滤，见 `pipeline.py`
- `merge_command_results` —— 跨多次命令的项目级聚合，见 `merge.py`（方案文档 §7.10）
- `parse_autoload_keys`   —— 解析 `project.godot` 的 `[autoload]` 段 key，见 `autoload.py`

生产路径（`verify_gate.tool.run_verify_tool`）直接调用上面三个入口。
旧的 `noise_filter.apply_noise_filter` 适配器已删除，不再保留第二套返回形状。
"""

from __future__ import annotations

from godot_mcp.verify_filter.autoload import parse_autoload_keys
from godot_mcp.verify_filter.merge import merge_command_results
from godot_mcp.verify_filter.pipeline import filter_verify_output

__all__ = [
    "filter_verify_output",
    "merge_command_results",
    "parse_autoload_keys",
]
