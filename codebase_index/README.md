# codebase_index — Godot 项目的代码索引与验证工具集

本目录实现《Godot Agent 代码索引与验证 —— 工业级实现指南 v2》中的 Layer 2 与 Layer 3。
设计原理见同目录 `design.md`，本 README 只负责"怎么跑起来"，不重复设计原理，避免两份文档漂移。

Layer 1（grep）不在本目录内：它没有专属代码，只是 Agent 系统提示里的一句用法说明，
外加被索引 Godot 项目根目录下的一个 `.rgignore`。

## 对外契约：只有两个入口

外部（Agent、CI 脚本）只依赖这两个入口，内部模块重构不影响调用方：

1. **`codeindex` / `codeindexd` 两个命令行可执行文件**（Layer 2，Python 实现）
   - `codeindex up`：幂等拉起 daemon，阻塞到首次全量索引完成再返回
   - `codeindex status` / `codeindex down`：daemon 生命周期管理
   - `codeindex find-symbol <name>`：精确查符号定义位置（文件/行号/所属类/签名）
   - `codeindex call-chain <name> --depth N`：递归 CTE 查询调用者链
   - `codeindex class-hierarchy <name>`：祖先链 + 子类列表
   - `codeindex sync <path>...`：同步重建指定文件索引（挂在 Agent 编辑工具写入完成后）
   - 所有查询命令统一 `--json` 输出；退出码：`0` 成功、`1` 查无结果、`2` daemon 未运行或索引明显过期
2. **一个 MCP server 启动入口**（Layer 3，Python 实现，见 `godot_mcp/`）
   - Agent 的 MCP 客户端配置指向：`python -m godot_mcp.server`（或 `uv run godot-mcp`）
   - 仅暴露一个工具：`verify`

## 环境依赖

- Python ≥ 3.11（两个子系统共用）
- `uv`（包管理）
- `rg`（ripgrep，Layer 1 用，Agent 直接 Bash 调用）
- `godot4` 二进制在 `PATH` 里（Layer 3 的校验子进程依赖）
- 被索引的 Godot 项目本身（路径通过配置指定，见下）

## 快速开始

```bash
# 1. 复制配置模板并按你的环境修改（config.yaml 已 gitignore，因人/项目而异）
cp config.example.yaml config.yaml

# 2. 一键装齐两个子系统的依赖
./scripts/bootstrap.sh

# 3. 拉起索引 daemon（首次会阻塞做全量扫描）
cd index && uv run codeindex up

# 4. 查询
uv run codeindex find-symbol take_damage --json
uv run codeindex call-chain take_damage --depth 3 --json

# 5. Layer 3 MCP server 由 Agent 的 MCP 客户端按需拉起，无需手动启动
```

## 运行时状态的位置

`index.db`、`daemon.lock`、`ready` 标记等运行时产物**不在本目录**，
统一放在被索引 Godot 项目根目录的 `.codeindex/` 下（配置里的 `index_state_dir`）。
本目录只装可提交的源码，可被任意多个 Godot 项目复用。

## 目录结构

```
codebase_index/
├── README.md               # 本文件
├── design.md               # 设计指南 v2（唯一权威设计文档）
├── config.example.yaml     # 共享配置模板
├── index/                  # Layer 2：daemon + CLI（Python）
├── godot_mcp/              # Layer 3：自建 MCP server（Python）
└── scripts/bootstrap.sh    # 一键安装两个子系统依赖
```

各子目录内部结构见各自的 README / pyproject.toml。
