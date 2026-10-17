# Godot 3→4 存量项目迁移收尾 Agent — 全局路标主文档 (Master LANDMARKS)

本文件是整个代码库的**顶层导航路标（Root Landmarks）**，汇总了代码库现状核查结论、去过度设计后的架构重构决策、已有模块的缺陷修补清单、新增模块的建设规划，以及通往各子目录 `LANDMARKS.md` 的层级跳转链接。

---

## 一、下级路标导航树（Hierarchical Landmarks Map）

> **跳转原则**：每个目录至多包含一份 `LANDMARKS.md`；点击下方链接可逐级下钻至对应模块或子模块的具体代码修改与实现指南。

* 📁 **[`inline_tools/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/LANDMARKS.md)** — Agent 原生工具包（`read` / `grep` 文档同步与写通道总览）
  * 📄 **[`inline_tools/editandfixguard/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/LANDMARKS.md)** — 唯一写通道与落盘守卫的 6 项代码缺陷修复指南
* 📁 **[`codebase_index/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/LANDMARKS.md)** — 代码/场景索引与 Godot 验证器总览及共享配置同步
  * 📁 **[`codebase_index/index/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/LANDMARKS.md)** — `codeindex` CLI 扩展（新增 `scene-freeze`）与文档修订
    * 📄 **[`codebase_index/index/src/codeindex/scene/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/LANDMARKS.md)** — `.tscn/.tres` 静态校验器（L4/L5）的 4 项核心 Bug 修复指南
  * 📄 **[`codebase_index/godot_mcp/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/LANDMARKS.md)** — `verify` 验证器状态隔离、快照触发补齐与移除 Redis 过度设计指南
* 📁 **[`rag/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/LANDMARKS.md)** — A/B 双层迁移知识库与混合检索器收尾总览
  * 📄 **[`rag/build/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/build/LANDMARKS.md)** — 编译脚本 `.prose.jsonl` 路径对齐与废弃占位脚本清理
  * 📄 **[`rag/retriever/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/retriever/LANDMARKS.md)** — 生产 `retriever.yaml` 最优超参回写与报错符号正则扩充
* 📁 **[`migration_agent/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/LANDMARKS.md)** — **【新增核心宿主包】** 顶层编排、配置与命令行入口指南
  * 📄 **[`migration_agent/l0/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/l0/LANDMARKS.md)** — **【新增】** L0 确定性预处理流水线（`intake` + `rule_codemod` + `trap_scan`）实现指南
  * 📄 **[`migration_agent/orchestrator/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/orchestrator/LANDMARKS.md)** — **【新增】** 进程内工具组合、LangGraph ReAct 循环与收尾门（`load_sweep`）实现指南
  * 📄 **[`migration_agent/trace/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/trace/LANDMARKS.md)** — **【新增】** SQLite 全链路可观测账本（`trace_store`）、断点续跑与审计报告实现指南
  * 📄 **[`migration_agent/eval/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/eval/LANDMARKS.md)** — **【新增】** Agent-as-Judge 语义审计、反向变异压测集生成与多进程批处理评测实现指南

---

## 二、架构反思与去过度设计决策（Architectural Reflection）

在全面审查真实代码后，我们对原初计划做出以下**四项建设性架构调整**，砍掉不必要的分布式基础设施包袱，聚焦于高 ROI 的核心能力：

### 1. 彻底砍掉 FastAPI 微服务与 Redis 协调层（用本地进程池 + 文件锁 + SQLite 替代）
* **为什么原计划的 Redis + 微服务是过度设计**：
  Godot 项目的迁移与校验强绑定本地磁盘工作区（`.godot/` 导入缓存、Git 工作树、`.codeindex/index.db`）。引入 FastAPI + Redis Streams + `XAUTOCLAIM` + 分布式租约锁，不仅增加运维与调试负担，而且在单机/CI 批处理场景下没有任何实质吞吐增益。
* **更优的轻量级替代方案**：
  1. **工作区物理隔离**：批处理 $N$ 个仓库时，每个仓库拥有独立的工作区目录 `workspaces/<repo_id>/`。现有的 POSIX `flock`（`.godot_mcp_verify.lock` 与 `.codeindex/daemon.lock`）已天然保证单工作区互斥，跨工作区**零锁竞争**。
  2. **本地进程池 + 信号量限流**：使用 Python 标准库 `concurrent.futures.ProcessPoolExecutor` 并发处理多个仓库；通过一个轻量级跨进程 `multiprocessing.Semaphore(max_godot_procs)`（或文件槽位锁）限制同时启动的 Godot headless 进程数，即可避免内存峰值 OOM。
  3. **SQLite 断点续跑替代 `RedisStateStore`**：每个工作区的每次 `verify`、每次 `edit`（对应一个 Git commit）和每次 RAG 检索都实时写入 SQLite `trace_store.db`。进程中断后重跑时，直接从 `trace_store.db` 恢复 `ProjectVerifyState`（轮次、签名历史、单文件补丁计数），无需 Redis 即可实现 100% 确定性的断点续跑（`--resume`）。

### 2. 进程内原生 Python 库调用（In-Process Composition）优先于跨进程 MCP 序列化
* 仓库现有的四大组件（`inline_tools`、`rag.retriever`、`codeindex`、`godot_mcp`）本质上都是同仓库的 Python 包（均可挂载到根虚拟环境）。
* 在实现 `migration_agent` 宿主编排器时，**保留 `codeindex` CLI 与 `godot-mcp` Server 作为对外兼容入口，但宿主内部直接通过 Python 函数调用**：
  * 直接调用 `godot_mcp.verify_gate.tool.run_verify_tool()`（省去 stdio MCP 进程启停与 JSON 序列化开销，`InMemoryStateStore` 自然常驻）。
  * 直接调用 `rag.retriever.retrieve_cached()`（进程内复用 LanceDB 与 BGE 模型句柄）。
  * 直接调用 `inline_tools.read` / `grep` / `editandfixguard.edit`。
  * 直接调用 `codeindex.db.queries` 与 `codeindex.scene.check.scene_check`。

### 3. 在 ReAct 循环前增加「依赖图根因排序（Dependency Root Triage）」
* Godot 中被 `preload` 或 `extends` 的基础脚本一旦报错，即使经过 `verify_filter` 过滤掉了明显的 `Failed to compile depended scripts`，仍可能同时暴露多个文件的 `root_cause_errors` 与 `pending_pointers`。
* 宿主在每轮 `verify` 后，利用 `codeindex` 的 `edges(kind IN ('preload', 'extends'))` 和 `verify` 的 `pointers[].target_res_path` 对根因做**拓扑排序**，把处于依赖图最底层的被依赖脚本排在 Top-1 喂给 LLM，避免 Agent 先改上游调用方而做无用功。

### 4. 将 L0 `rule_codemod` 拆分为「启动期全仓确定性批处理」与「循环内按需符号重写」
* **启动期（Pre-Loop）**：在 `--convert-3to4` 之后，仅对 `rules.db` 中**无上下文歧义**的全局类名/内置类型/全局枚举重命名（`symbol_kind IN ('class', 'builtin', 'singleton')` 且 `owner IS NULL`）做全仓 `.gd` AST + `.tscn/.tres` `type=` 批量替换。这既补齐了转换器跳过的 >4MB 大文件，又吃掉了 4.0→4.7.1 的类名变更，且**绝不误伤同名用户函数**。
* **循环期（In-Loop）**：对于带 `owner` 约束的方法/属性重命名（如 `PackedScene.instance -> instantiate`），不搞全仓盲替，而是在 `verify` 报错定位到具体行、且 `retrieve_migration_rule` 命中 `agent_action == 'apply_rename'` 时，直接用确定性行内替换或携带 `rule_id` 交由 `edit` 工具落地。

---

## 三、全局状态与待办总表（Master Checklist）

### Phase 0：已有模块缺陷修复与接口对齐（先决条件）

| 编号 | 模块 | 核心修复项 | 详细路标链接 |
| :--- | :--- | :--- | :--- |
| **M0-1** | `inline_tools/editandfixguard` | 1. `__init__.py` 导出 `edit` 等公开 API<br>2. `edit.py` 接入判据 5 (`check_rename_consistency`)<br>3. 修复 `_verify_on_disk` 对存量带病场景误回滚的 Bug<br>4. 补齐 `create` 模式下的 `check_symbols(G5.1)` 及 `.gdshader/.godot/.cfg` 通用守卫<br>5. `git_txn.py` 清理临时 `.patch` 文件 | [查看详情](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/LANDMARKS.md) |
| **M0-2** | `codebase_index/index` | 1. **修复 `scene/rules.py` 查询表名 `rules` 与实际 `migration_rules` 不一致导致 `E_UNMIGRATED_TYPE` 失效的严重 Bug**<br>2. `cli.py` 新增 `codeindex scene-freeze` 子命令接通 `freeze_baseline()`<br>3. 修复 `scene/check.py` 增量 `--path` 模式下将未扫描场景误判为 `fixed` 的 Bug<br>4. 修复 `scene/baseline.py` 中 `E_MEMBER_GONE` 的脚本归属校验与 `LIMIT 1` 漏报 | [查看详情](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/LANDMARKS.md) |
| **M0-3** | `codebase_index/godot_mcp` | 1. **修复 `tool.py` 中 `check_file` 与 `check_workspace` 共用 `signature_history` 导致假震荡熔断的严重 Bug**<br>2. `algorithm.py` 增加 `circuit_state == "OPEN"` 入口短路<br>3. `snapshot.py` / `trigger.py` 补齐 `.tscn`/`.godot` 快照后缀与 UID 双端触发<br>4. `tool.py` 绑定 `config.yaml` 路径；移除 `state_store.py` 中未使用的 `RedisStateStore` | [查看详情](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/LANDMARKS.md) |
| **M0-4** | `rag` | 1. 统一 `build/` 与 `test/` 中 `.prose.jsonl` 的路径引用，清理 `:memory:.ses` 与废弃 stub<br>2. 将评测最优超参（`bm25.k=20, vector.k=20, weight=0.3:0.7, recall_k=20`）回写至 `retriever.yaml`<br>3. 扩充 `router.extract_symbols()` 的报错提取正则 | [查看详情](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/LANDMARKS.md) |

### Phase 1 ~ Phase 3：新增核心模块建设（`migration_agent/`）

| 阶段 | 子模块目录 | 待实现的核心功能 | 详细路标链接 |
| :--- | :--- | :--- | :--- |
| **Phase 1** | `migration_agent/trace/` | SQLite 全链路账本 (`TraceStore`)、`TraceRetrievalObserver`、本地断点恢复 (`resume_state`)、单仓结构化迁移审计报告生成 (`report.py`) | [查看详情](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/trace/LANDMARKS.md) |
| **Phase 1** | `migration_agent/l0/` | 1. `intake.py`：工作区拷贝、`.gitignore` 注入、>4MB 大文件预检、`--convert-3to4`、`.uid` 清理、首次 V3 导入、Git `B0` 提交、全量索引与 `scene-freeze`<br>2. `codemod.py`：基于 Tree-sitter AST Span 与场景 `type=` Span 的零 Token 确定性重命名引擎<br>3. `trap_scan.py`：`static_scan_post_l0` 语义陷阱静态扫描器（如 `extents -> size`） | [查看详情](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/l0/LANDMARKS.md) |
| **Phase 2** | `migration_agent/orchestrator/` | 1. `tools.py`：注入宿主上下文的 6 个结构化工具封装（严禁 Bash）<br>2. `load_sweep.py`：收尾门 `ResourceLoader.load()` 遍历脚本生成、哨兵归因与崩溃续跑<br>3. `graph.py`：LangGraph ReAct 状态机、依赖根因排序、L1/L2 模型升降级路由、恶化自动 Revert、以及收尾门（`verify CLEAN` + `scene-check` + `load_sweep`） | [查看详情](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/orchestrator/LANDMARKS.md) |
| **Phase 3** | `migration_agent/eval/` | 1. `judge.py`：独立 LLM 语义保真度裁判（Agent-as-Judge）与人工一致性校准<br>2. `reverse_mutator.py`：Godot 4.x 健康项目退化变异生成器（产出带精确 Ground Truth 的 B 集）<br>3. `batch_runner.py`：基于 `ProcessPoolExecutor` + 本地 Godot 进程信号量的多仓并发评测与消融实验执行器 | [查看详情](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/eval/LANDMARKS.md) |

---

## 四、根级环境与包管理改造指导

在进入 Phase 1 开发前，需在仓库根 [`pyproject.toml`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/pyproject.toml) 中将 `godot-mcp`、`rag` 以及新建的 `migration_agent` 纳入统一工作区环境（遵守两层包管理规范，不在 `migration_agent/` 下另建 `pyproject.toml`）：

```toml
[project]
name = "godot-migration-agent"
version = "0.1.0"
description = "Godot 3->4 迁移收尾 Agent：仓库根项目聚合（codeindex / godot_mcp / rag / inline_tools / migration_agent）"
requires-python = ">=3.11"
dependencies = [
  "tree-sitter>=0.23",
  "tree-sitter-language-pack>=1.9",
  "pydantic>=2.7",
  "pyyaml>=6.0",
  "langgraph>=0.2",
  "langchain-core>=0.3",
  "codeindex",
  "godot-mcp",
  "rag",
]

[project.scripts]
migrate-godot = "migration_agent.cli:main"

[tool.uv.sources]
codeindex = { path = "codebase_index/index", editable = true }
godot-mcp = { path = "codebase_index/godot_mcp", editable = true }
rag = { path = "rag", editable = true }

[tool.pytest.ini_options]
testpaths = [
  "inline_tools/tests",
  "inline_tools/editandfixguard/tests",
  "migration_agent/tests",
]
```
