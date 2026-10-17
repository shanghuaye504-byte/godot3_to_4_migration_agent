# `migration_agent/l0` — L0 确定性预处理流水线

本子模块负责零 Token 消耗的确定性迁移阶段：工作区隔离拷贝、Git 事务仓库初始化、执行 `godot --headless --convert-3to4`、基于 `rules.db` 的两阶段 AST 规则重写、静默运行时陷阱预扫描，以及首次代码索引构建与场景基线冻结。

详细实现规范参见：[`LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/l0/LANDMARKS.md)。
