# `migration_agent/trace` 模块路标 (LANDMARKS)

> **上级路标**：[`migration_agent/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/LANDMARKS.md)
> **叶子节点**：本目录无下级子目录路标。

## 1. 模块职责与设计目标

在移除过度设计的 Redis 与微服务层后，`migration_agent/trace/` 使用**本地轻量级 SQLite 数据库（`.migration_trace.db`，开启 WAL 模式）**承担三大核心职责：
1. **迁移轨迹持久化与断点续跑（`--resume`）**：记录每个仓库、每一轮迭代的诊断快照、Patch 事务、Gate 决策与 Token 消耗；进程中断后重启可从最后一个 `COMMITTED` 轮次无缝恢复。
2. **跨仓库 LLM 响应缓存（`llm_fix_cache`）**：以 `sha256(error_signature + normalized_code_slice + rule_ids)` 为键缓存验证通过的修复方案，在批量迁移几十个仓库时直接命中同类 API 破坏性变更，实现可量化的 Token 降本。
3. **机器可读与人类可读审计报告生成（`report.py`）**：汇总 L0 预处理、L1/L2 修复轨迹、残留错误与 Judge 评审结果，产出 `migration_report.json` 与 `MIGRATION_REPORT.md`。

本目录包含以下 2 个源码文件：
- `store.py`：SQLite 状态、轨迹与跨仓库缓存存储实现。
- `report.py`：单仓库与批处理汇总报告生成器。

---

## 2. 逐文件实现指导

### 2.1 `store.py` — 本地 SQLite 轨迹与缓存存储

#### 数据库表结构设计（Schema）：
```sql
PRAGMA journal_mode = WAL;

-- 1. 仓库级运行主表（支持断点续跑与成本统计）
CREATE TABLE IF NOT EXISTS repo_runs (
    repo_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    workspace_path TEXT NOT NULL,
    status TEXT NOT NULL,              -- RUNNING / CLEAN / PARTIAL / ESCALATED
    model_tier TEXT NOT NULL,          -- L1 / L2 / RULE_ONLY
    initial_error_count INTEGER DEFAULT 0,
    final_error_count INTEGER DEFAULT 0,
    rounds_used INTEGER DEFAULT 0,
    l0_replacements INTEGER DEFAULT 0,
    llm_cache_hits INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0.0,
    gate_state_json TEXT,              -- 序列化后的 WorkspaceVerifyState，供 --resume 恢复
    escalation_reason TEXT,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. 轮次与 Patch 审计明细表
CREATE TABLE IF NOT EXISTS round_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id TEXT NOT NULL,
    round_idx INTEGER NOT NULL,
    target_file TEXT,
    error_signatures_json TEXT NOT NULL,
    patch_commit_sha TEXT,
    diff_text TEXT,
    cited_rule_ids_json TEXT,
    guard_status TEXT,                 -- COMMITTED / REJECTED / ROLLED_BACK
    gate_action TEXT,                  -- PASS / CONTINUE / UPGRADE_MODEL_TIER / ROLLBACK_AND_RETRY / ...
    judge_verdict_json TEXT,           -- Agent-as-Judge 审计结果
    tokens_used INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    created_at TEXT NOT NULL
);

-- 3. 跨仓库 LLM 修复缓存表
CREATE TABLE IF NOT EXISTS llm_fix_cache (
    cache_key TEXT PRIMARY KEY,        -- sha256(error_category + symbol + normalized_line + rule_id)
    old_line_pattern TEXT NOT NULL,
    new_line_replacement TEXT NOT NULL,
    rule_id TEXT,
    hit_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
```

#### 核心类与方法签名：
```python
class TraceStore:
    def __init__(self, db_path: Path) -> None: ...
    def init_or_resume_run(self, repo_id: str, source_path: Path, workspace_path: Path) -> dict | None: ...
    def save_round_trace(self, trace: RoundTraceRecord, gate_state: WorkspaceVerifyState) -> None: ...
    def finalize_run(self, repo_id: str, status: str, final_error_count: int, escalation_reason: str | None = None) -> None: ...
    def lookup_fix_cache(self, cache_key: str) -> tuple[str, str] | None: ...
    def save_fix_cache(self, cache_key: str, old_line: str, new_line: str, rule_id: str | None) -> None: ...
```

---

### 2.2 `report.py` — 迁移审计报告生成器

迁移服务的核心交付物不是聊天对话，而是结构化的审计报告。`report.py` 需从 `TraceStore` 读取指定 `repo_id` 的完整轨迹，生成两份文件：

1. **`<workspace>/migration_report.json`**（供评测脚本与 CI 机器消费）：
   - 包含 `repo_id`、`status`（`CLEAN` / `PARTIAL` / `ESCALATED`）、`parse_clean`（`bool`）、`error_reduction_rate`（`1 - final_errors / max(1, initial_errors)`）。
   - `l0_summary`：`convert_3to4` 耗时、`codemod` 替换次数、节省的估算 Token 占比。
   - `patches`：每个保留在最终分支上的 Commit SHA、修改文件、解决的 Error Signatures、引用的 RAG 规则 ID，以及 **Agent-as-Judge 的评分与评语**。
   - `suspicious_patches`：被 Judge 标记为 `verdict == "SUSPICIOUS"` 或 `"FAKE_FIX"`（如删代码、改 `pass`）的 Patch 列表，提醒人工重点复核。
   - `residual_errors`：尚未解决的 `Diagnostic`、`SceneProblem` 与 `StaticTrapFinding` 清单。
   - `metrics`：总耗时、迭代轮数、L1/L2 调用次数、LLM 缓存命中次数、总成本（`$`）。

2. **`<workspace>/MIGRATION_REPORT.md`**（供开发者快速审阅）：
   - 使用清晰的 Markdown 表格呈现上述核心指标、可疑修复 Diff 摘录与残留问题修复建议。
