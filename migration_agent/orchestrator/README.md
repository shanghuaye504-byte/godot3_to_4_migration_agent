# `migration_agent/orchestrator` — L1/L2 LangGraph ReAct 修复编排器

本子模块负责基于 `langgraph` 的智能体修复循环：按脚本依赖拓扑排序的 Error Triage、进程内 7 大工具封装、L1→L2→Rule-Only 三级降级链，以及收尾阶段的全量 `.gd`/`.tscn` `load()` 验证扫描。

详细实现规范参见：[`LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/orchestrator/LANDMARKS.md)。
