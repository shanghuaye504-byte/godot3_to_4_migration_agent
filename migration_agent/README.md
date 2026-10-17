# `migration_agent` — Godot 3→4 批量迁移收尾 Agent 主控包

本目录为 Godot 3→4 存量项目批量迁移收尾 Agent 的顶层编排与评测包，以进程内 Python 库调用方式串联 `rag`、`codebase_index/index`、`codebase_index/godot_mcp` 与 `inline_tools`。

详细实现指导与子模块导航请参见本目录路标文档：[`LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/LANDMARKS.md)。

## 子模块概览

- [`l0/`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/l0/README.md)：L0 确定性预处理流水线（官方 `--convert-3to4`、两阶段 AST `rule_codemod`、静默陷阱扫描、索引构建与基线冻结）。
- [`orchestrator/`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/orchestrator/README.md)：L1/L2 LangGraph ReAct 修复编排器、Error Triage 与收尾全量 `load()` 扫描。
- [`trace/`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/trace/README.md)：本地 SQLite 轨迹持久化、断点续跑、跨仓库 LLM 修复缓存与迁移报告导出。
- [`eval/`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/eval/README.md)：Agent-as-Judge 语义保真评审、反向变异数据集生成器与多仓库本地并发批处理运行器。
