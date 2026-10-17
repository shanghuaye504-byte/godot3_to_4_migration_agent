# `codebase_index/index/src/codeindex/scene` 模块路标 (LANDMARKS)

> **上级路标**：[`codebase_index/index/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/LANDMARKS.md)
> **叶子节点**：本目录无下级子目录路标。

## 1. 模块现状与已核实的 Bug 清单

`scene/` 子包实现了 `.tscn` 场景与 `.tres` 资源的四层静态检查器（L1 文本语法、L2 引用存在性、L3 跨图绑定与信号、L4 规则库与类层级契约）以及基线对比系统。

经源码逐行核查，发现以下 **3 个必须修复的功能缺陷** 与 **1 处代码清理项**：

| 编号 | 文件与行号 | 问题描述 | 严重度 |
| :--- | :--- | :--- | :--- |
| **SCN-BUG-1** | [`rules.py:109`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/rules.py#L109) | **SQLite 表名不匹配导致 `E_UNMIGRATED_TYPE` 永久失效**：`_load_migrated_types()` 硬编码查询 `SELECT old_symbol FROM rules WHERE symbol_kind = 'class'`，而 `rag/artifacts/rules.db` 中的真实表名为 `migration_rules`（单元测试 fixture 用的是 `rules`）。连接真实 `rules.db` 时抛出 `sqlite3.OperationalError: no such table: rules`，在第 114 行被捕获后返回 `rules_unavailable = True` | **致命 (P0)** |
| **SCN-BUG-2** | [`check.py:46-89`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/check.py#L46-L89)、[`baseline.py:86-135`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/baseline.py#L86-L135) | **增量检查（`--path`）误报全库其余场景已修复 (`fixed`)**：当传入 `paths` 参数时，`run_scene_check()` 仅检查受影响闭包内的 `scene_files`，但 `diff_baseline(conn, all_problems)` 却与整张 `scene_baseline` 表全量对比，导致所有未纳入本次检查范围的场景基线问题全部被归入 `diff.fixed` | **高 (P0)** |
| **SCN-BUG-3** | [`baseline.py:138-167`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/baseline.py#L138-L167) | **`E_MEMBER_GONE` 缺少脚本归属校验且被 `LIMIT 1` 截断**：① `kind == 'func'` 时仅按 `kind = 'conn_method' AND symbol = ?` 查询 `scene_refs`，未校验连接目标节点（`to_path`）挂载的脚本是否为被删函数的 `script_path`，同名回调会跨脚本误报；② SQL 末尾带有 `LIMIT 1`，若多个场景引用了被删类或方法，只报告 1 处 | **高 (P1)** |
| **SCN-CLN-1** | [`resolve.py:217`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/resolve.py#L217) | 冗余三元表达式：`node_path = name if not model.root_paths else name` 分支两侧完全相同 | **低 (P2)** |

---

## 2. 逐项修复指导

### 2.1 修复 [`rules.py:98-116`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/rules.py#L98-L116) 中的 `rules.db` 表名自适应 (`SCN-BUG-1`)

参考 [`inline_tools/editandfixguard/rules_db.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/rules_db.py) 的做法，在 `_load_migrated_types(rules_db_path)` 中先探测 `sqlite_master`，同时兼容生产环境表名 `migration_rules` 与单元测试表名 `rules`：

```python
def _load_migrated_types(rules_db_path: Path | None) -> tuple[set[str], bool]:
    """返回 (migrated_class_names, rules_unavailable)。"""
    if rules_db_path is None or not rules_db_path.exists():
        return set(), True
    try:
        uri = f"file:{rules_db_path}?mode=ro"
        rconn = sqlite3.connect(uri, uri=True, timeout=2.0)
        try:
            tables = {
                row[0]
                for row in rconn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "migration_rules" in tables:
                table_name = "migration_rules"
            elif "rules" in tables:
                table_name = "rules"
            else:
                return set(), True
            rows = rconn.execute(
                f"SELECT old_symbol FROM {table_name} WHERE symbol_kind = 'class'"
            ).fetchall()
            return {r[0] for r in rows if r[0]}, False
        finally:
            rconn.close()
    except sqlite3.Error as exc:
        logger.warning("Failed to load rules.db (%s): %s", rules_db_path, exc)
        return set(), True
```

---

### 2.2 修复 [`baseline.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/baseline.py) 与 [`check.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/check.py) 的增量基线对比 (`SCN-BUG-2`)

1. 在 [`baseline.py:86`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/baseline.py#L86) 中，为 `diff_baseline` 增加可选参数 `checked_scenes: set[str] | None = None`：
   - 当 `checked_scenes is not None` 时，从 `scene_baseline` 读取的 `baseline_map` 仅保留 `path in checked_scenes` 的行（或仅对 `fp, (code, path)` 中 `path in checked_scenes` 的条目计算 `fixed_fps`）：

```python
def diff_baseline(
    conn: sqlite3.Connection,
    current: list[SceneProblem],
    checked_scenes: set[str] | None = None,
) -> tuple[bool, BaselineDiff]:
    ...
    # 计算 fixed_fps 时，仅针对本次实际检查过的场景：
    fixed_fps = [
        fp for fp in (set(baseline_map) - set(current_map))
        if checked_scenes is None or baseline_map[fp][1] in checked_scenes
    ]
```

2. 在 [`check.py:46-89`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/check.py#L46-L89) 的 `run_scene_check()` 中：
   - 当 `paths` 非空时，将 `checked_scenes = set(scene_files)` 传给 `diff_baseline(conn, all_problems, checked_scenes=checked_scenes)`；当全量检查（`not paths`）时传 `checked_scenes=None`。
   - 对 `member_gone_problems(conn)` 返回的问题，若 `paths` 非空，同样仅保留 `p.location.path in checked_scenes` 的问题纳入 `all_problems`。

---

### 2.3 修复 [`baseline.py:138-167`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/baseline.py#L138-L167) 中的 `E_MEMBER_GONE` 归属检查与多场景覆盖 (`SCN-BUG-3`)

在 `member_gone_problems(conn: sqlite3.Connection) -> list[SceneProblem]` 中：
1. **去掉 `LIMIT 1`**：将 `.fetchone()` 改为遍历 `.fetchall()`，确保所有引用了被删类或回调方法的场景都能报错。
2. **校验 `conn_method` 的目标节点脚本归属**：
   - 当 `kind == "func"`（来自 `script_path` 的方法 `name` 被删除）时，查询 `scene_refs` 中 `kind = 'conn_method' AND symbol = ?` 的行 `(scene_path, line, col, to_node_path)`。
   - 若该场景在 `scene_nodes` 中存在挂载了 `script_path` 的节点（可通过查询该场景中 `scene_refs(kind='script_ref', symbol=script_path)` 绑定的 `node_path` 集合），则检查 `to_node_path` 是否在该脚本绑定节点集合内（若该场景根本没有挂载 `script_path`，则直接跳过，避免同名 `_on_timeout` 跨脚本误报）。

---

### 2.4 清理 [`resolve.py:217`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/resolve.py#L217) (`SCN-CLN-1`)

> **注意**：切勿将根节点的 `node_path` 从 `name` 改为 `"."`，因为现有测试套件 [`tests/scene/test_resolve.py:16-34`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/tests/scene/test_resolve.py#L16-L34) 与数据库外键契约明确约定根节点 `node_path` 为根节点名称（如 `"Main"`），且 `resolve_rel_path(model, ".", "Child")` 已在 [`resolve.py:293-294`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/resolve.py#L293-L294) 中专门将 `"."` 映射到 `model.root_paths[0]`。

仅需将 [`resolve.py:217`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/src/codeindex/scene/resolve.py#L217) 的冗余条件表达式简化为：

```python
if parent is None:
    node_path = name
    model.root_paths.append(node_path)
```

---

## 3. 单元测试补充要求

在 [`codebase_index/index/tests/scene/`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/index/tests/scene/) 下补充以下测试用例：
1. `test_rules.py`：新增使用 `migration_rules` 表名的 SQLite 数据库测试，验证 `_load_migrated_types` 能正确加载 `old_symbol` 且 `rules_unavailable == False`。
2. `test_baseline.py`：
   - 验证冻结含 2 个报错场景（`a.tscn`, `b.tscn`）的基线后，仅对 `a.tscn` 执行增量 `run_scene_check(conn, paths=["a.tscn"])` 时，`b.tscn` 的基线问题**不会**出现在 `diff.fixed` 中。
   - 验证当 `enemy.gd` 删除 `_on_hit` 函数时，仅挂载了 `player.gd`（也有 `_on_hit` 连接）的场景不会误报 `E_MEMBER_GONE`。
