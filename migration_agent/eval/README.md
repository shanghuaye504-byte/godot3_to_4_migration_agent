# `migration_agent/eval` — Agent-as-Judge 与批处理评测套件

本子模块包含独立审查 Git Diff 语义保真度的 Agent-as-Judge、生成带精确 Ground Truth 退化样本的 Godot 4→3 反向变异器，以及基于本地进程池与 Godot 进程信号量的多仓库并发批处理运行器。

详细实现规范参见：[`LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/eval/LANDMARKS.md)。
