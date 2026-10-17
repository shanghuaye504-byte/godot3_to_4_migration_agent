# `migration_agent` 核心主控包路标 (LANDMARKS)

> **上级路标**：[根目录 `LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/LANDMARKS.md)

## 1. 下级路标导航 (Child Landmarks)

`migration_agent/` 是串联已有四大底座（`rag`、`codeindex`、`godot_mcp`、`inline_tools`）完成 Godot 3→4 端到端无人值守迁移的核心主控包。各子模块的详细实现指导分别位于以下子目录路标中：

- **[`l0/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/l0/LANDMARKS.md)**：L0 确定性预处理流水线（工作区拷贝与 Git 事务初始化、`--convert-3to4` 执行、两阶段确定性 `rule_codemod`、全库静默陷阱正则预扫描、`codeindex build` 与 `scene-freeze`）。
- **[`orchestrator/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/orchestrator/LANDMARKS.md)**：L1/L2 LangGraph ReAct 编排器（基于依赖根因的 Error Triage、进程内 7 大工具封装、L1→L2→Rule-Only 三级降级链、收尾全量 `load()` 扫描节点）。
- **[`trace/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/trace/LANDMARKS.md)**：本地 SQLite 轨迹与审计持久化（替代原计划中的 Redis 状态层，支持断点续跑 `--resume`、跨仓库 LLM 修复缓存与 JSON/Markdown 迁移报告导出）。
- **[`eval/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/eval/LANDMARKS.md)**：评测与批处理套件（Agent-as-Judge 语义保真度评审、Godot 4→3 反向变异生成器、基于本地进程池 + Godot 进程信号量的多仓库批处理运行器）。

---

## 2. 顶层 CLI 与统一配置实现指导

除上述四个子目录外，`migration_agent/` 顶层需实现以下两个入口文件：

| 文件 | 核心职责 |
| :--- | :--- |
| `migration_agent/config.py` | 统一加载并校验运行配置（`MigrationConfig`），统一管理 `workspace_root`、`godot_bin`、`rules_db_path`、`rag_config_path`、L1/L2 模型名称、单仓库预算上限（`max_rounds`、`max_cost_usd`）及本地 `trace_db_path` |
| `migration_agent/cli.py` | 暴露统一命令行入口 `migrate-agent`，支持单仓库迁移（`run`）、多仓库并发批处理（`batch`）、反向变异评测集生成（`mutate`）与独立 Judge 审计（`judge`） |

---

### 2.1 `migration_agent/config.py` 设计规范

```python
from dataclasses import dataclass, field
from pathlib import Path

@dataclass(frozen=True)
class MigrationConfig:
    repo_root: Path
    godot_bin: Path = Path("/Applications/Godot.app/Contents/MacOS/Godot")
    rules_db_path: Path = Path("rag/artifacts/rules.db")
    rag_config_path: Path = Path("rag/retriever/config/retriever.yaml")
    trace_db_path: Path = Path(".migration_trace.db")
    # 模型分级与预算控制
    l1_model: str = "gpt-4o-mini"
    l2_model: str = "claude-3-7-sonnet-latest"
    judge_model: str = "gpt-4o"
    max_rounds: int = 20
    max_react_steps_per_round: int = 8
    max_cost_usd: float = 1.50
    convert_timeout_ms: int = 180_000
    verify_timeout_ms: int = 60_000
    enable_llm_cache: bool = True
```

---

### 2.2 `migration_agent/cli.py` 子命令设计

使用 `argparse` 实现以下 4 个子命令，并在根 `pyproject.toml` 注册 `[project.scripts] migrate-agent = "migration_agent.cli:main"`：

1. **`migrate-agent run --source <3x_repo> --output <4x_workspace> [--resume] [--rule-only]`**
   - 调用 `l0.run_l0_pipeline()` 完成工作区准备、官方转换、确定性 codemod、索引构建与基线冻结。
   - 调用 `orchestrator.run_migration_graph()` 执行 ReAct 修复循环与收尾全量 `load()` 扫描。
   - 调用 `eval.judge.evaluate_workspace_diffs()` 对所有已提交 Patch 进行语义审计。
   - 调用 `trace.report.generate_migration_report()` 输出 `<output>/MIGRATION_REPORT.md` 与 `migration_report.json`。

2. **`migrate-agent batch --repos-dir <dir> --output-dir <out> --workers 2 --max-godot-procs 2`**
   - 调用 `eval.batch_runner.run_batch()` 并发迁移多个仓库，并生成汇总对比表 `batch_summary.md`。

3. **`migrate-agent mutate --source <4x_clean_repo> --output <mutated_dir> --count 50`**
   - 调用 `eval.reverse_mutator.generate_mutations()` 生成带精确 Ground Truth 的反向退化样本集。

4. **`migrate-agent judge --workspace <4x_workspace>`**
   - 对指定工作区中的 Git 历史 Patch 单独运行 Agent-as-Judge 并输出审计报告。
