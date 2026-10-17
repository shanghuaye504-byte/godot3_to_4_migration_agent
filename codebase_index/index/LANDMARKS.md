# `codebase_index/index` 模块路标 (LANDMARKS)

> **上级路标**：[`codebase_index/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/LANDMARKS.md)

## 1. 下级路标导航 (Child Landmarks)

- **[`src/codeindex/scene/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/LANDMARKS.md)**：`.tscn` 场景语义检查器（L1–L4 规则、基线冻结、增量对比与 `rules.db` 表名适配修复）。

---

## 2. 模块现状与待修复问题清单

`codebase_index/index`（包名 `codeindex`）已完成 `.gd`（基于 `tree-sitter-gdscript`）、`.tscn`/`.tres`（状态机解析）、`project.godot` 的解析、SQLite 落盘（Schema v2）、`watchdog` 增量守护进程以及 CLI 查询命令。

经代码走查核实，本模块（除 `scene/` 子目录外）需要完成以下改进与修复：

| 编号 | 文件与行号 | 问题描述 | 严重度 |
| :--- | :--- | :--- | :--- |
| **IDX-BUG-1** | [`src/codeindex/cli.py:32-96`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/cli.py#L32-L96) | 缺少 `scene-freeze` 子命令：虽然 [`scene/baseline.py:33`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/baseline.py#L33) 已实现 `freeze_baseline(conn, problems)`，但 `cli.py` 与 `daemon.py` 均无入口调用它，导致 `scene_baseline` 和 `scene_member_baseline` 永远为空（`baseline_frozen=False`） | **高 (P0)** |
| **IDX-BUG-2** | [`src/codeindex/config.py:45-70`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/config.py#L45-L70) | `rules_db_path` 在 `config.yaml` 中配置为相对路径（如 `../rag/artifacts/rules.db`）时，`load_config()` 直接使用 `Path(raw).expanduser().resolve()`，其基准目录是当前工作目录（CWD）而非 `config.yaml` 所在目录，导致从其他目录调用时找不到 `rules.db` | **中 (P1)** |
| **IDX-FEAT-1** | [`src/codeindex/cli.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/cli.py) / 新增辅助函数 | 缺少供 Orchestrator Error Triage 直接调用的**脚本依赖拓扑排序接口**：当多个脚本同时报错时，Agent 需要查询 `relations` 表（`extends` / `preload`）找出处于依赖树底层的“根因脚本” | **中 (P1)** |
| **IDX-DOC-1** | [`README.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/README.md) | 架构树注释仍将 `scene/` 标注为“骨架，实现见设计文档”，且 CLI 列表未包含 `scene-freeze` | **低 (P2)** |

---

## 3. 详细修复与实现指导

### 3.1 新增 `codeindex scene-freeze` CLI 命令与 API (`IDX-BUG-1`)

在 L0 `--convert-3to4` 执行完毕并首次构建 `.codeindex.db` 后，必须立即冻结场景基线（记录转换后已存在的固有场景问题与脚本成员快照），后续 L1/L2 Agent 修改代码或场景时，`scene-check` 才能精确区分 `new_caused_by_edit`、`pre_existing` 与 `fixed`。

#### 修改步骤：
1. 在 [`src/codeindex/scene/check.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/check.py) 中新增 `run_scene_freeze(conn: sqlite3.Connection, rules_db_path: Path | None = None) -> int`：
   - 扫描 `scene_files` 表中所有状态为 `OK` 或 `MALFORMED` 的场景路径。
   - 对每个场景执行 `check_scene(conn, scene_path, migrated_types, rules_unavailable)` 收集全量 `all_problems`。
   - 在事务 `with conn:` 中调用 `freeze_baseline(conn, all_problems)`，返回写入 `scene_baseline` 的问题总数。
2. 在 [`src/codeindex/cli.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/cli.py) 的 `build_parser()` 中注册 `scene-freeze` 子命令：

```python
p_sfreeze = sub.add_parser("scene-freeze", help="冻结当前工作区的场景检查基线與脚本成员快照")
p_sfreeze.add_argument("--json", action="store_true", help="输出 JSON 格式结果")
```

3. 在 [`src/codeindex/cli.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/cli.py) 中实现 `cmd_scene_freeze(config: Config, as_json: bool) -> int`，使用 `connect_rw(config.db_path)` 打开读写连接并调用 `run_scene_freeze(conn, config.rules_db_path)`。

---

### 3.2 修复 `config.py` 中 `rules_db_path` 相对路径解析 (`IDX-BUG-2`)

在 [`src/codeindex/config.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/config.py) 中解析 `rules_db_path` 时：
- 如果 `rules_db_raw` 是相对路径，优先相对于 `config_path.parent` 解析（若存在），若不存在再回退到相对于 `workspace_root` 解析：

```python
if rules_db_raw:
    candidate = Path(rules_db_raw).expanduser()
    if not candidate.is_absolute() and config_path is not None:
        rel_to_cfg = (config_path.parent / candidate).resolve()
        if rel_to_cfg.exists():
            candidate = rel_to_cfg
        else:
            candidate = (workspace_root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    rules_db_path = candidate
```

---

### 3.3 新增报错脚本依赖根因排序辅助函数 (`IDX-FEAT-1`)

在 [`src/codeindex/db/queries.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/db/queries.py) 中新增 `rank_root_cause_files(conn: sqlite3.Connection, error_files: list[str]) -> list[str]`：
- 查询 `relations` 表与 `symbols` 表，构建 `error_files` 集合内部的依赖有向图（若脚本 `A.gd` `extends` 或 `preload` 了 `B.gd` 或 `B.gd` 定义的 `class_name`，则 `A -> B`）。
- 计算每个报错脚本在报错子图中的出度（即它所依赖的其他**也在报错**的脚本数量）。
- 优先返回出度为 `0`（不依赖任何其他报错脚本）且入度最高（被最多其他脚本依赖）的根因脚本列表，供 `migration_agent/orchestrator` 的 Triage 节点使用。

---

## 4. 验证要求

修改完成后，在 `codebase_index/index/` 目录下运行测试套件：

```bash
uv run pytest
```

确保原有测试与新增的 `scene-freeze`、增量 `scene-check` 测试全部通过，随后同步更新 [`README.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/README.md)。
