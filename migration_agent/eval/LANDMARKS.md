# `migration_agent/eval` 模块路标 (LANDMARKS)

> **上级路标**：[`migration_agent/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/LANDMARKS.md)
> **叶子节点**：本目录无下级子目录路标。

## 1. 模块职责与设计目标

`migration_agent/eval/` 负责回答两个决定项目含金量的核心问题：
1. **“编译器过了，但代码逻辑有没有被 Agent 偷偷改坏？”** —— 通过独立的 **Agent-as-Judge (`judge.py`)** 审查每一个已提交的 Git Diff，产出与客观 `parse-clean` 率正交的**语义保真率（Semantic Fidelity Rate）**。
2. **“如何在有 Ground Truth 的前提下大规模压测并横向扩展？”** —— 通过 **反向变异生成器 (`reverse_mutator.py`)** 从干净的 Godot 4.x 仓库合成带完美 Ground Truth 的退化样本，并通过 **本地多进程批处理运行器 (`batch_runner.py`)** 安全并发地处理多仓库。

本目录包含以下 3 个源码文件：
- `judge.py`：独立 LLM 语义审计器（Agent-as-Judge）。
- `reverse_mutator.py`：Godot 4→3 反向变异数据集生成器。
- `batch_runner.py`：基于 `ProcessPoolExecutor` 与本地 Godot 进程信号量的批处理调度器。

---

## 2. 逐文件实现指导

### 2.1 `judge.py` — Agent-as-Judge 语义保真度评审器

#### 核心输出契约（Pydantic Schema）：
```python
from typing import Literal
from pydantic import BaseModel, Field

class JudgeVerdict(BaseModel):
    commit_sha: str
    file_path: str
    verdict: Literal["SEMANTIC_SAFE", "SUSPICIOUS", "FAKE_FIX"]
    score: int = Field(ge=1, le=5, description="1=破坏逻辑的假修复, 3=存疑需人工看, 5=精确等价迁移")
    failure_mode: Literal[
        "NONE",
        "DELETED_LOGIC",           # 直接删除或注释掉报错代码行
        "STUBBED_WITH_PASS",       # 将函数体替换为 pass 或固定返回值骗过编译器
        "COROUTINE_ORDER_BROKEN",  # yield 改 await 时语句执行顺序错乱
        "SIGNAL_SEMANTICS_LOST",   # 断开信号或吞掉回调参数
        "HALLUCINATED_API",        # 换成了语义不匹配的另一个 API
    ] = "NONE"
    rationale: str = Field(description="简明中文审计理由，指出具体行号与风险")
```

#### 实现要点：
1. **输入上下文构建**：
   - 提取目标 Commit 的 `git show <sha>` Unified Diff。
   - 提取该 Patch 声称解决的 `Diagnostic`（报错信息）以及当时检索引用的 `MigrationRule`（`old_symbol -> new_symbol` 及 `migration_note`）。
2. **双阶段检查（先规则快筛，再 LLM 深审）**：
   - **静态快筛**：对比修改前后的 AST 有效语句数。如果一个 Patch 解决了报错，但删除了 `>= 3` 行函数调用且未新增对应调用，或新增了裸 `pass` 且原函数体非空，直接标为 `SUSPICIOUS` 并提示 Judge LLM 重点核查。
   - **独立 LLM 评审**：调用 `config.judge_model`（强制使用 `with_structured_output(JudgeVerdict)`），按 Rubric 打分并写回 `TraceStore.round_traces.judge_verdict_json`。

---

### 2.2 `reverse_mutator.py` — Godot 4→3 反向变异生成器

以项目中已验证零报错的 [`godot_test/clean-control-4x/`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/godot_test/clean-control-4x)（或其他健康 Godot 4.x 仓库）为基准，反向注入 Godot 3.x 破坏性语法，构造拥有 **100% 逐字精确 Ground Truth** 的评测集。

#### 支援的 5 类反向变异算子（Mutation Operators）：
1. **`OP_CLASS_DOWNGRADE`**：查询 `rules.db` 中 `symbol_kind == 'class'` 的高置信规则，将 `.gd` 和 `.tscn` 中的 Godot 4 类名退化回 Godot 3 类名（如 `CharacterBody2D -> KinematicBody2D`、`Node3D -> Spatial`、`AnimatedSprite2D -> AnimatedSprite`、`Time.get_ticks_msec -> OS.get_ticks_msec`）。
2. **`OP_METHOD_DOWNGRADE`**：将 `.instantiate()` 退化为 `.instance()`，`.is_empty()` 退化为 `.empty()`，`FileAccess.open(...)` 退化为 Godot 3 `File.new()` 模式。
3. **`OP_ANNOTATION_DOWNGRADE`**：将 `@export` 退化为 `export`，`@onready` 退化为 `onready`。
4. **`OP_AWAIT_TO_YIELD`**：将 `await <expr>.<signal>` 退化为 `yield(<expr>, "<signal>")`。
5. **`OP_CONNECT_TO_STRING`**：将 `sig.connect(_on_func)` 退化为 `connect("sig", self, "_on_func")`。

#### 输出产物结构：
每次变异在输出目录下生成一个独立样本子目录 `sample_001/`，并写入 `ground_truth.json`：
```json
{
  "sample_id": "sample_001",
  "operator": "OP_CLASS_DOWNGRADE",
  "file_path": "res://scripts/player.gd",
  "line": 12,
  "ground_truth_rule_id": "class:KinematicBody2D->CharacterBody2D",
  "original_4x_content": "...",
  "mutated_3x_content": "..."
}
```
由此可直接计算：
- **Exact-Match 修复率**：迁移后文件与 `original_4x_content` 忽略空白符后的完全一致率。
- **RAG Recall@5**：报错触发检索时，`ground_truth_rule_id` 出现在 Top-5 检索结果中的比例。

---

### 2.3 `batch_runner.py` — 本地多仓库批处理与信号量控制

在不引入 Redis 和微服务的条件下，安全高效地并发跑完 `godot_test/` 下的全部测试仓库（如 `godot-3-2d-day-night-cycle-demo`、`3d-squash-the-creeps`、`dodge-the-creeps`、`gdquest-2d-finite-state-machine`、`2d-GDQuest-grid-based-movement` 及变异样本集）：

#### 核心并发安全设计：
1. **目录级天然隔离（无需分布式锁）**：
   - 每个待迁移仓库在启动前都会在 `output_dir/<repo_name>/` 下创建独立的副本工作区、独立的 `.godot/` 缓存与独立的 `<workspace>/.codeindex.db`，从根源上消除并发写冲突。
2. **Godot 进程全局信号量（防止内存打满）**：
   - 每个 `godot --headless` 子进程峰值消耗 300MB–600MB 内存。
   - 使用 `multiprocessing.Manager().BoundedSemaphore(max_godot_procs)`（默认 `max_godot_procs = 2`）包裹 Godot 子进程调用，确保即使开启 4 个 Python Worker 并发执行 RAG 检索与 LLM 推理，同一时刻最多只有 `max_godot_procs` 个 Godot 引擎进程在运行。
3. **汇总评测表生成（`batch_summary.md`）**：
   - 批处理结束后，自动聚合所有仓库的 `migration_report.json`，输出包含以下维度的 Markdown 汇总表：
     - 仓库名 | 初始 Error 数 | L0 后 Error 数 | 最终 Error 数 | Error 削减率 | Parse-Clean | Judge 语义保真率 | 迭代轮数 | LLM 缓存命中 | 耗时 (s) | 成本 ($)
