# godot_mcp/ — Layer 3：Godot 校验 MCP server（Python 实现）

本目录只暴露一个 MCP 工具 `verify`，用于在 Agent 修改后拿到 Godot 4.x 的客观解析/编译信号。

> **范围降级说明**：原 Layer 3 规划包含 LSP（`hover_symbol` / `workspace_symbol`）+
> `verify` 共三个工具。由于 LSP 会引入不可预测的进程/端口冲突，且时间紧张，
> 现决定**完全去掉 LSP 方案**，本目录只保留 `verify`。
> Layer 2 的符号查询继续由 `../index/` 的 `codeindex` CLI 承担，不经过 MCP。

## 工具表面积：仅一个

| 工具 | 输入 | 说明 |
| --- | --- | --- |
| `verify` | `kind: "check_file" \| "check_workspace"`；`check_file` 必填 `target` | `check_file`→COLD 时先 V3 再 V2；WARM 只跑 V2，filter/merge 后做 A/B 外壳标注（`class_cache_stale` / 未登记 autoload caveat）。`check_workspace` 走外壳（内部组装 phase/diff，相关后缀快照 ≤2000 个文件 / 1 GiB，超限硬拒），**不**做 A/B 标注。studio 一对一，不收 session/成本参数 |

`verify` 内部现在是 `godot_mcp.verify_gate.run_verify_tool` 的薄封装：先用
`godot_mcp.verify_filter` 把 Godot 原始输出过滤/合并成 `ProjectFilterView`，
`check_file` 再做 A/B 外壳标注，然后用 `godot_mcp.verify_gate.algorithm.evaluate`
判定这一轮相对历史处于什么状态（继续/无进展/单文件卡住/震荡/轮次耗尽/
基础设施熔断）。对 LLM 而言，返回值是 `VerifyGateResult`（过滤结果 + Gate 判定），
`hard_stop=True` 时宿主 Agent 循环会在工具调用返回后强制结束会话。

对外输入/输出字段、以及 Agent 参数如何接到内部 `run_verify_tool`，见
[`docs/mcp_verify_tool_interface.md`](docs/mcp_verify_tool_interface.md)。

## 环境依赖

- Python ≥ 3.11（`.python-version` 钉在 3.11，与 `../index/` 一致，避免本机其他
  Python 版本被 `uv` 误选中）
- `uv`（包管理，子模块独立一层，见根 `common_rules.mdc` 的分层约定）
- `godot4` 二进制在 `PATH` 中（校验子进程依赖它）
- `../config.yaml`（从 `../config.example.yaml` 复制；本包只读其中的
  `project_root` / `godot_binary` 两个字段，见 `config.py` 文件头）

```bash
cd codebase_index/godot_mcp
uv sync --all-groups        # 安装运行 + dev 依赖（pytest / pytest-timeout）
uv run python -c "import godot_mcp"   # 确认包能 import
uv run pytest tests/                  # 自动化测试
uv run godot-mcp                      # stdio MCP server（工具列表里只有 verify）
```

## 目录结构与权限边界

```text
src/godot_mcp/
├── config.py            # 读共享 config.yaml，只取 project_root / godot_binary
├── server.py            # MCP server 入口，仅注册 verify 一个工具
├── verify/
│   ├── commands.py      # VERIFY_COMMANDS：探针子集 V1 / V2 / V3
│   ├── sentinel.py      # V1 哨兵脚本生成与删除
│   └── runner.py        # 一次性子进程；V1 时写/删哨兵 + timeout + 进程组 kill
├── verify_filter/       # 噪声过滤纯函数包
├── verify_shell/        # 外壳：锁 / 拒收 / UID / 触发表 / V1↔V2 采集
└── verify_gate/         # 重试门：config / state_store / algorithm / tool

tests/
├── test_config.py       # config.py 的纯函数测试
├── test_commands.py     # VERIFY_COMMANDS 白名单回归保护
├── test_sentinel.py     # 哨兵扫描 / 写删 / 空项目
├── test_runner.py       # runner 子进程语义（假二进制，不依赖 godot4）
├── test_verify_tool.py  # run_verify_tool 胶水层（mock 子进程）
├── test_server.py       # MCP 工具列表 / ToolError / 结构化返回
├── verify_shell/...     # 外壳叶子模块 + 采集循环
├── verify_filter/...    # verify_filter 黄金测试
└── verify_gate/...      # verify_gate 算法 / 状态 / 配置测试
```

`verify/commands.py` 是唯一定义"能跑哪些 Godot 命令"的地方（key 是 V1/V2/V3）；
`verify/runner.py` 负责一次性子进程的超时、进程组 kill，以及 V1 哨兵的写入/删除。

## 调试

校验子进程命令行是常量，直接在终端手动跑一遍 `VERIFY_COMMANDS` 里那条命令，
对比过滤前后的输出，永远可复现。
