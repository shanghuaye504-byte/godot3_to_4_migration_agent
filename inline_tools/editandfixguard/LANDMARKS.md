# `inline_tools/editandfixguard/` 缺陷修复与完善路标 (LANDMARKS)

> **上级路标**：[`inline_tools/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/LANDMARKS.md)  
> **下级路标**：*(当前为叶子节点，无下级路标文档)*

本目录实现了 Agent 的唯一写通道 `edit()` 与写前/写后守卫 `fix_guard`。虽然 `NEXT_STEP.md` 中的 Step 0–10 已全部勾选，但经源码级审查，仍存在 **6 处必须修补的断线与逻辑漏洞**。

---

## 一、待修复的 6 项代码缺陷（含精确行号与修改方案）

### 修复 1：在 `__init__.py` 中导出公开 API
* **问题位置**：[`inline_tools/editandfixguard/__init__.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/__init__.py) 目前仅有注释，未导出任何符号，违反了 [`NEXT_STEP.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/NEXT_STEP.md#L41) 第 41 行的约定。
* **修改方案**：
  ```python
  """唯一写通道 edit 与落盘前守卫 fix_guard。"""

  from .anchor import Hunk, apply_hunks
  from .edit import SCENE_REGRESSION, SYNTAX_BROKEN, edit
  from .guard import GuardResult, GuardViolation, verdict
  from .precheck import precheck

  __all__ = [
      "Hunk",
      "apply_hunks",
      "SCENE_REGRESSION",
      "SYNTAX_BROKEN",
      "edit",
      "GuardResult",
      "GuardViolation",
      "verdict",
      "precheck",
  ]
  ```

---

### 修复 2：将判据 5（`check_rename_consistency`）接入 `edit.py`
* **问题位置**：[`scene_names.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/scene_names.py#L96) 已实现 `check_rename_consistency(project_root, *, renamed, db_path)`，但 [`edit.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/edit.py#L59) 接收了 `db_path: Path | None = None` 后从未在函数体内使用，也从未调用 `check_rename_consistency`。
* **修改方案**：
  1. 在 [`symbols.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/symbols.py) 中增加一个纯函数 `detect_renamed_symbols(file: str, old_text: str, new_text: str) -> dict[str, str]`：
     * 当 `old_text` 与 `new_text` 的 AST error 节点数均为 0 时，提取前后的 `(kind, name)` 集合 `before` 与 `after`。
     * 对于 `kind in {"class", "func", "signal"}`，计算 `removed_by_kind[k] = {n for (kind, n) in before - after if kind == k}` 与 `added_by_kind[k] = {n for (kind, n) in after - before if kind == k}`。
     * 若某个 `kind` 下既有被删名字又有新增名字（说明是改名而非纯删除，符合 `NEXT_STEP.md` 第 135 行「`.gd` 上 class/func/signal 改名（不是纯删除）时」的定义），将 `old_name -> next(iter(added_by_kind[k]))` 放入 `renamed` 字典返回。
  2. 在 [`edit.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/edit.py#L121) 第 121 行之后追加：
     ```python
     renamed = symbols.detect_renamed_symbols(res_file, old_text, new_text)
     if renamed:
         guard_results.append(
             scene_names.check_rename_consistency(root, renamed=renamed, db_path=db_path)
         )
     ```

---

### 修复 3：修复 `edit.py` 中 `_verify_on_disk` 误杀存量带病场景的严重 Bug
* **问题位置**：[`edit.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/edit.py#L184-L197) 第 193–196 行：
  ```python
  elif suffix in _SCENE:
      from codeindex.scene.rules import check_scene
      if check_scene(on_disk.decode(), res_file).problems:
          return SCENE_REGRESSION
  ```
* **原因分析**：写前判据 `scene_names.check_scene_invariants(res_file, old_text, new_text)` 比较的是差集 `post - pre`（允许场景存在历史遗留问题，只拦截新增回归）。但 `_verify_on_disk` 只要看到场景有任何存量 `problems`（比如另一个节点还没修好），就会直接返回 `SCENE_REGRESSION` 并触发 `git_txn.rollback`！
* **修改方案**：给 `_verify_on_disk` 传入 `old_text: str`，对 `_SCENE` 分支调用 `scene_names.check_scene_invariants(res_file, old_text, on_disk.decode("utf-8"))`，仅当 `not inv.ok` 时返回 `SCENE_REGRESSION`。

---

### 修复 4：补齐 `kind == "create"` 时的 G5.1 反向迁移检查与偷懒检查
* **问题位置**：[`edit.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/edit.py#L103) 第 103 行写为 `if suffix == _GD and kind != "create":`。
* **原因分析**：[`symbols.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/symbols.py#L72-L81) 第 72–81 行专门为 `create`（`old_text == ""`）实现了跳过判据 2、只检查 G5.1（防止新建脚本里使用 Godot 3 旧符号）以及检查新文件自身是否有语法错误的逻辑，却被 `edit.py` 的 `kind != "create"` 短路跳过了。
* **修改方案**：当 `suffix == _GD and kind == "create"` 时，执行：
  * `symbols.check_symbols(res_file, "", new_text, declared_scope=declared_scope, rules_db_path=rules_db_path)`
  * 若 `symbols._error_node_count(new_text) > 0`，报 `SYNTAX_REGRESSION`
  * `guard.check_lazy_fix(udiff, file=res_file)`

---

### 修复 5：补齐 `.gdshader` / `.godot` / `.cfg` 的通用写前守卫
* **问题位置**：[`edit.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/edit.py#L103-L124) 只处理了 `suffix == _GD` 和 `suffix in _SCENE`。
* **修改方案**：对于 `precheck.ALLOWED_SUFFIXES` 中的另外三类文本后缀（`.gdshader`、`.godot`、`.cfg`），当 `kind != "create"` 时，同样运行与 AST 无关的三条通用文本守卫：
  * `guard.check_blast_radius(...)`
  * `guard.check_deletion(...)`
  * `guard.check_lazy_fix(...)`

---

### 修复 6：清理 `git_txn.py` 中的临时补丁文件
* **问题位置**：[`git_txn.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/git_txn.py#L52-L76) 的 `apply_check()` 和 `apply_index()` 使用 `NamedTemporaryFile(..., delete=False)` 后未删除临时文件。
* **修改方案**：用 `try ... finally: Path(patch_path).unlink(missing_ok=True)` 包裹 `_git(...)` 调用。

---

## 二、执行与验收 Checklist

- [ ] 完成修复 1–6 的代码改动。
- [ ] 在 [`tests/test_edit_flow.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/tests/test_edit_flow.py) 中新增 3 个端到端测试用例：
  1. `test_edit_gd_rename_triggers_inconsistent_rename_warn`：修改 `.gd` 函数名且 `.tscn` 仍引用旧名时，`edit()` 返回 `ok=True` 且 `guard["verdict"] == "warn"`，含 `INCONSISTENT_RENAME`。
  2. `test_edit_scene_with_preexisting_error_succeeds_if_no_new_regression`：编辑带存量 `E_NOT_CONVERTED` 的 `.tscn` 的某处合法属性，验证 `_verify_on_disk` 不会误触发 `SCENE_REGRESSION`。
  3. `test_create_gd_with_old_symbol_rejected_by_reverse_migration`：`kind="create"` 新建含旧符号的 `.gd` 被 G5.1 拦截。
- [ ] 更新 [`inline_tools/editandfixguard/README.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/README.md)（删除「当前只有本说明和空 `__init__.py`」的滞后表述）。
- [ ] 运行 `uv run pytest inline_tools/tests inline_tools/editandfixguard/tests -q` 确保全部通过。
