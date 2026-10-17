# `migration_agent/orchestrator` 模块路标 (LANDMARKS)

> **上级路标**：[`migration_agent/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/LANDMARKS.md)
> **叶子节点**：本目录无下级子目录路标。

## 1. 模块职责与架构定位

`migration_agent/orchestrator/` 实现单仓库迁移的核心智能体闭环（基于 `langgraph.graph.StateGraph`）。它以**进程内 Python 库调用**的方式整合：
- `godot_mcp.verify_shell.execute_verify_shell`（客观验证与门控）
- `codeindex`（SQLite 符号/依赖/场景检查）
- `rag.retriever.retrieve`（混合检索迁移规则与修复示例）
- `inline_tools`（`read_file`、`grep`、`editandfixguard.edit_file`）

本目录需实现以下 5 个源码文件：
1. `state.py`：LangGraph 状态与 Pydantic 结构化契约定义。
2. `tools.py`：供 ReAct 模型自主调用的 7 个本地进程内工具封装。
3. `load_sweep.py`：收尾阶段的全量 `.gd` / `.tscn` `load()` 验证器（弥补 `--check-only` 的盲区）。
4. `prompts.py`：Triage 与 ReAct 修复 Agent 的系统提示词。
5. `graph.py`：StateGraph 节点定义、条件边路由与三级降级策略（L1 → L2 → Rule-Only）。

---

## 2. 状态图与控制流设计 (`graph.py`)

```
[verify_and_gate]
   │  调用 execute_verify_shell("check_workspace") + run_scene_check()
   ├── gate.action == "PASS" 且 scene/trap 清零 ──► [final_load_sweep]
   │                                                    ├── 全通过 ──► [END (CLEAN)]
   │                                                    └── 发现隐藏错误 ──► 注入诊断回流 [triage_errors]
   ├── gate.hard_stop == True (OSCILLATION / CIRCUIT_OPEN / MAX_ROUNDS) ──► [END (ESCALATED)]
   ├── gate.action == "ROLLBACK_AND_RETRY" ──► 自动回滚上一 Patch ──► [triage_errors]
   └── gate.action in ("CONTINUE", "UPGRADE_MODEL_TIER") ──► [triage_errors]
                                                                 │
                                                                 ▼
                                                       [triage_errors]
                                         1. 用 codeindex.rank_root_cause_files 按依赖拓扑排序
                                         2. 锁定当前批次唯一根因脚本 + 预取 RAG Top-3 规则
                                         3. 根据 model_tier / no_progress_streak 选择 L1 / L2 / Rule-Only
                                                                 │
                                                                 ▼
                                                       [react_repair_loop]
                                         模型自主调用 read_file / grep_symbol / query_index /
                                         retrieve_migration_rule / edit_file / check_single_file
                                         (当成功提交 1~3 个关联 Patch 或达单轮步数上限时返回 verify_and_gate)
```

---

## 3. 逐文件实现指导

### 3.1 `state.py` — LangGraph 状态契约

```python
from typing import Literal, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing import Annotated

class MigrationGraphState(TypedDict):
    workspace: str
    round_idx: int
    model_tier: Literal["L1", "L2", "RULE_ONLY"]
    # 最新一轮验证结果
    gate_action: str
    hard_stop: bool
    active_diagnostics: list[dict]
    scene_problems: list[dict]
    pending_traps: list[dict]
    # Triage 选出的当前主攻目标
    target_file: str | None
    target_diagnostics: list[dict]
    prefetched_rules: list[dict]
    # Patch 与成本追踪
    applied_patches: list[dict]
    touched_files_this_round: list[str]
    total_cost_usd: float
    status: Literal["RUNNING", "CLEAN", "PARTIAL", "ESCALATED"]
    escalation_reason: str | None
    messages: Annotated[list[AnyMessage], add_messages]
```

---

### 3.2 `tools.py` — 7 个进程内 Agent 工具封装

使用 `@langchain_core.tools.tool` 封装以下 7 个工具，通过闭包绑定当前工作区的 `workspace_root`、`.codeindex.db` 与 `rules.db`：

1. **`read_file(path: str, offset: int = 1, limit: int = 120) -> dict`**
   - 直接调用 `inline_tools.read.read_file(path, offset=offset, limit=limit, workspace_root=ws)`。
2. **`grep_symbol(pattern: str, path: str | None = None, glob: str | None = None) -> dict`**
   - 直接调用 `inline_tools.grep.grep(pattern, path=path, glob=glob, output_mode="content", workspace_root=ws)`。
3. **`query_index(action: Literal["find_symbol", "find_refs", "get_file_outline", "get_dependencies"], target: str) -> dict`**
   - 直接调用 `codeindex.db.queries` 中的对应查询函数，让 Agent 瞬间获取符号定义位置、全库引用点或脚本继承链。
4. **`check_scene_consistency(paths: list[str] | None = None) -> dict`**
   - 调用 `codeindex.scene.check.run_scene_check(conn, paths=paths, rules_db_path=rules_db)`，返回 JSON 序列化后的 `CheckReport`。
5. **`retrieve_migration_rule(query: str, error_code: str | None = None, top_k: int = 5) -> dict`**
   - 调用 `rag.retriever.retrieve(RetrievalQuery(query=query, error_code=error_code, top_k=top_k))` 并返回精简后的 `rule_hits`（`old_symbol`, `new_symbol`, `migration_note`）与 `chunk_hits`（`heading_path`, `text`, `code_blocks`）。
6. **`edit_file(file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> dict`**
   - 调用 `inline_tools.editandfixguard.edit_file(...)`。
   - **关键联动**：若返回 `status == "COMMITTED"`，将 `file_path` 记录到当前轮次的 `touched_files_this_round` 列表中，以便下一轮传给 `execute_verify_shell(..., touched_files=...)` 触发必要的 V3 重导。
7. **`check_single_file(res_path: str) -> dict`**
   - 调用 `godot_mcp.verify_shell.execute_verify_shell("check_file", target=res_path)`，供 Agent 在修改单个 `.gd` 脚本后快速验证局部语法，无需等待全库检查。

---

### 3.3 `load_sweep.py` — 收尾阶段全量 `load()` 扫描器

#### 为什么必须有 `load_sweep.py`？
项目在 [`godot_test/probe_tests/reports/README.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/godot_test/probe_tests/reports/README.md) 中的实测报告已经证明：
- `godot --headless --check-only --quit` **即使不带 `--script` 参数，也只会检查启动链（autoload 与 main_scene）触达的脚本**！未挂载到启动链的独立脚本或子场景不会被解析。
- 而对每个文件单独起一次 Godot 进程又存在冷启动开销与跨脚本循环依赖死锁风险。

#### 实现方案：
在 `verify_and_gate` 判定 `PASS`（主启动链 error 清零）后，进入 `final_load_sweep` 节点：
1. 在工作区临时生成（验证后删除）一个轻量级 Headless 扫描脚本 `.godot_migration_sweep.gd`（继承 `SceneTree`）：
   - 扫描工作区内全部 `.gd`、`.tscn`、`.gdshader` 文件列表，依次调用 `ResourceLoader.load(res_path, "", ResourceLoader.CACHE_MODE_IGNORE)`。
2. 通过 `godot_mcp.verify.runner` 执行一次 `godot --headless --check-only -s res://.godot_migration_sweep.gd --quit`。
3. 用 `godot_mcp.verify.parser` 与 `verify_filter` 解析输出。若发现任何未被引用的脏脚本或损坏场景报错，将其转化为 `active_diagnostics` 送回 `triage_errors` 继续修复；若 0 错误，才正式宣布整库 `CLEAN`。

---

### 3.4 三级降级链与死循环保护 (`graph.py`)

1. **L1 默认层（小模型 + RAG）**：初始 `model_tier = "L1"`，处理单文件 API 替换、信号连接改写、注解迁移。
2. **L2 升级层（大模型）**：当 `verify_gate` 返回 `action == "UPGRADE_MODEL_TIER"`（即连续 `no_progress_limit` 轮错误签名集未缩减）或 Triage 发现错误涉及跨文件基类签名重构时，自动将 `model_tier` 切换为 `"L2"`。
3. **Rule-Only 兜底层（零 LLM 降级）**：当 LLM 接口连续报 429/5xx 错误或单仓库累计成本达到 `max_cost_usd` 时，自动切换为 `model_tier = "RULE_ONLY"`，调用 `l0.codemod.apply_targeted_codemod()` 仅执行 `rules.db` 确定性映射，随后输出 `PARTIAL` 迁移报告并安全退出。
