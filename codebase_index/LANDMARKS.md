# `codebase_index` 模块路标 (LANDMARKS)

> **上级路标**：[根目录 `LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/LANDMARKS.md)

## 1. 下级路标导航 (Child Landmarks)

本目录包含两个核心子包，其详细修复与完善指导分别位于各自子目录的 `LANDMARKS.md` 中：

- **[`index/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/LANDMARKS.md)**：Godot 符号/资源/场景 SQLite 索引器（`codeindex`），含增量构建、FTS5 全文检索、CLI 查询及 `.tscn` 场景语义检查（下辖 [`index/src/codeindex/scene/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/LANDMARKS.md)）。
- **[`godot_mcp/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/LANDMARKS.md)**：Godot Headless 验证流水线与 MCP 服务（`godot-mcp`），含 `verify`、`verify_filter`、`verify_gate`、`verify_shell` 四阶段验证栈。

---

## 2. 模块职责与现状评估

`codebase_index/` 提供两项基础设施：
1. **符号与场景索引 (`codebase_index/index/`)**：解析 `.gd`、`.tscn`、`.tres`、`project.godot`，写入 SQLite 数据库 `.codeindex.db`，支持符号定义/引用查询、依赖图查询以及 `.tscn` L1–L4 静态一致性校验。
2. **客观验证闭环 (`codebase_index/godot_mcp/`)**：封装 Godot 4.6 `--headless` CLI 子进程执行，解析 stderr 生成结构化诊断，过滤级联故障与已知假阳性，驱动重试/震荡/熔断状态机，并在需要时自动执行 V3 一次性全量修复重导与快照回滚。

### 已核实的跨包协同与文档过期问题

| 问题编号 | 位置 | 问题描述 | 修复目标 |
| :--- | :--- | :--- | :--- |
| **CI-DOC-1** | [`design.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/design.md)、[`NEXT_STEP.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/NEXT_STEP.md) | 仍将 `codeindex/scene/` 标注为“仅骨架 / 待实现”，将 `godot_mcp` 标注为“只有 `run_verify` stub”，与已完成的代码严重脱节 | 更新文档以反映 `scene` 9 个模块与 `godot_mcp` 四层验证栈均已落地的事实 |
| **CI-CFG-1** | [`config.yaml`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/config.yaml) | `rules_db_path` 当前为相对路径 `../rag/artifacts/rules.db`，当从项目根目录启动 CLI 或 Agent 时解析路径易发生偏移；且未显式列出 `retry_gate` 配置段 | 支持相对于 `config.yaml` 所在目录解析 `rules_db_path`，并补充 `retry_gate` 默认配置段 |

---

## 3. 本级目录修改指导

### 3.1 修正 [`config.yaml`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/config.yaml) 默认配置

在 [`codebase_index/config.yaml`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/config.yaml) 中补齐 `retry_gate` 配置段，确保 `godot_mcp` 与 `codeindex` 共享一致的配置文件结构：

```yaml
workspace_root: "/Users/yy_catmax/Desktop/pingfan/godot3_to_4_migration_agent/godot_test/godot-3-2d-day-night-cycle-demo"
db_path: ".codeindex.db"
rules_db_path: "../rag/artifacts/rules.db"
godot_bin: "/Applications/Godot.app/Contents/MacOS/Godot"

# 传给 godot 子进程的额外环境变量
godot_env: {}

# 重试门控与熔断配置
retry_gate:
  max_rounds_per_workspace: 20
  no_progress_limit: 2
  repeated_patch_limit: 3
  infra_breaker_threshold: 3
  allow_v3_auto_repair: true
```

### 3.2 同步更新本目录文档

完成 [`index/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/LANDMARKS.md) 与 [`godot_mcp/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/LANDMARKS.md) 中的代码修复后：
1. 在 `codebase_index/` 下创建或更新就地 [`README.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/README.md)，概述 `index` 与 `godot_mcp` 的职责边界与进程内调用方式。
2. 更新 [`NEXT_STEP.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/NEXT_STEP.md)，将已完成的 Step 1–4 标记为已完成。
