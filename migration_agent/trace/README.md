# `migration_agent/trace` — 本地 SQLite 轨迹存储与报告生成

本子模块使用本地 SQLite 数据库（`.migration_trace.db`）持久化单仓库与多仓库的迁移轨迹、门控状态（支持 `--resume` 断点续跑）与跨仓库 LLM 修复缓存，并导出 `migration_report.json` 与 `MIGRATION_REPORT.md`。

详细实现规范参见：[`LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/trace/LANDMARKS.md)。
