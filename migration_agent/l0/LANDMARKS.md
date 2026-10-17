# `migration_agent/l0` 模块路标 (LANDMARKS)

> **上级路标**：[`migration_agent/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/migration_agent/LANDMARKS.md)
> **叶子节点**：本目录无下级子目录路标。

## 1. 模块职责与设计目标

`migration_agent/l0/` 负责 **零 Token 消耗的确定性预处理流水线（L0 阶段）**。它的目标是在唤醒 LLM Agent 之前，用确定性工具吃掉 80% 以上的机械重命名，并把转换器遗留的“静默运行时陷阱”提前暴露为结构化待办项。

本目录需实现以下 3 个源码文件：
1. `intake.py`：工作区隔离拷贝、Git 事务仓库初始化、调用 `godot --headless --convert-3to4`、构建 `.codeindex.db` 并执行 `scene-freeze`。
2. `codemod.py`：基于 `rag/artifacts/rules.db` 与 `tree-sitter-gdscript` 的两阶段确定性 AST 重写器。
3. `trap_scan.py`：针对 `--check-only` 抓不到的 Godot 3→4 静默语义陷阱进行全库预扫描。

---

## 2. 逐文件实现指导

### 2.1 `intake.py` — 工作区接管与官方转换器封装

#### 核心函数签名：
```python
@dataclass
class L0IntakeResult:
    workspace: Path
    base_commit_sha: str
    convert_commit_sha: str | None
    codemod_commit_sha: str | None
    convert_timed_out: bool
    convert_exit_code: int
    frozen_scene_problems: int
    codemod_replacements: int

def run_l0_pipeline(
    source_repo: Path,
    target_workspace: Path,
    config: MigrationConfig,
) -> L0IntakeResult: ...
```

#### 实现要点：
1. **隔离工作区初始化**：
   - 若 `target_workspace` 不存在，使用 `shutil.copytree(source_repo, target_workspace, ignore=shutil.ignore_patterns(".git", ".godot", ".import"))` 拷贝源码。
   - 初始化独立 Git 仓库（`git init` -> `git add -A` -> `git commit -m "chore(l0): baseline godot 3 source"`），确保 `inline_tools/editandfixguard/git_txn.py` 的快照与回滚拥有干净的工作树基线。
2. **安全调用 `--convert-3to4`**：
   - 检查 `project.godot` 中的 `config_version`。若 `config_version < 5`（即 Godot 3.x 项目），使用 `godot_mcp.verify.runner.run_subprocess`（带独立进程组与 `convert_timeout_ms` 超时强杀）运行：
     `godot --headless --path <workspace> --convert-3to4`
   - 提交转换结果：`git commit -am "chore(l0): official --convert-3to4"`。
3. **执行 `codemod.py`（Phase A 确定性替换）**：
   - 调用 `apply_global_codemod(target_workspace, config.rules_db_path)`，若产生修改则提交：`git commit -am "chore(l0): deterministic rule_codemod"`。
4. **首次构建代码索引与场景基线冻结**：
   - 调用 `codeindex` 的全量扫描与写入逻辑生成 `<workspace>/.codeindex.db`。
   - 调用 `codeindex.scene.check.run_scene_freeze(conn, config.rules_db_path)` 冻结 L0 转换后的场景基线。

---

### 2.2 `codemod.py` — 两阶段确定性规则重写器

#### 为什么不能盲目全局正则替换？
`rag/artifacts/rules.db` 中共有 6,626 条结构化迁移规则，但其中大量的 `method` / `property` / `signal` / `enum` 规则（如 `instance -> instantiate`、`empty -> is_empty`）可能与用户自定义同名函数冲突。因此必须实现**两阶段策略**：

#### Phase A：L0 无条件安全替换（`apply_global_codemod`）
仅筛选 `rules.db` 中满足 `confidence >= 0.9` 且无歧义的规则：
1. **全局类/单例重命名（`symbol_kind == 'class'`）**：如 `KinematicBody2D -> CharacterBody2D`、`Spatial -> Node3D`、`OS.get_ticks_msec -> Time.get_ticks_msec`。
   - 使用 `tree-sitter-gdscript` 解析每个 `.gd` 文件的 AST，仅替换 `identifier` / `type` 节点（自动避开字符串字面量与注释）。
2. **`.tscn` / `.tres` 节点与资源类型重命名**：
   - 仅替换 `[node ... type="OldClass"]` 与 `[ext_resource ... type="OldClass"]` 头部属性中的 `OldClass -> NewClass`。

#### Phase B：验证报错驱动的受控替换（`apply_targeted_codemod`）
供 Orchestrator 在 L1/L2 降级（`rule_only` 模式）或 Triage 预处理时调用：
- 输入 `VerifyResult` 中的 `Diagnostic` 列表。
- 当报错为 `UNDECLARED_IDENTIFIER` 或 `NONEXISTENT_FUNCTION`，且报错行的 `extracted_symbols` 在 `rules.db` 中存在**唯一**的 `new_symbol` 映射（如 `.instance()` -> `.instantiate()`，`.empty()` -> `.is_empty()`）时，仅对该报错行对应的 AST 节点执行替换。

---

### 2.3 `trap_scan.py` — 静默运行时陷阱预扫描器

Godot 4 的 `--headless --check-only` 只能捕获编译期语法与类型错误，无法捕获**合法语法但语义已坏**或**不纳入脚本检查范围**的静默陷阱。`trap_scan.py` 需扫描全工作区并输出 `list[StaticTrapFinding]`：

```python
@dataclass(frozen=True)
class StaticTrapFinding:
    trap_id: str          # 如 "TRAP_SHADER_3X", "TRAP_TWEEN_NODE", "TRAP_YIELD_RESIDUAL", "TRAP_EXPORT_HINT"
    rel_path: str
    line: int
    snippet: str
    suggestion: str
```

#### 必检的 5 类静默陷阱规则：
1. **`TRAP_SHADER_3X`**：扫描 `.gdshader`、`.shader` 及 `.tscn` 内嵌 `Shader` 子资源，检测残留的 Godot 3 着色器内置变量/关键字（如 `TIME` 以外的 `TEXTURE_PIXEL_SIZE` 误用、`hint_albedo` -> `source_color`、`hint_black_albedo`、`world_vertex_coords` 等——issue #63673 证明 `--check-only` 不会检查 `.gdshader`）。
2. **`TRAP_YIELD_RESIDUAL`**：扫描 `.gd` 文件中残留的 `yield(` 调用或转换器生成的错误 `await` 语法。
3. **`TRAP_TWEEN_NODE`**：检测 `.gd` 或 `.tscn` 中残留的 Godot 3 `Tween` 节点调用模式（如 `.interpolate_property(`、`.interpolate_callback(`，Godot 4 必须改为 `create_tween().tween_property(...)`）。
4. **`TRAP_CONNECT_CALLABLE`**：检测残留的 Godot 3 字符串风格 `.connect("signal_name", target, "method_name", binds, flags)` 五参数/四参数调用。
5. **`TRAP_SETGET_SYNTAX`**：检测残留的 Godot 3 `setget setter_func, getter_func` 语法。

扫描出的 `StaticTrapFinding` 列表将直接注入 Orchestrator 的 `MigrationState.pending_traps`，与编译器报错一同纳入修复队列。
