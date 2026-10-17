# `inline_tools/` 模块路标文档 (LANDMARKS)

> **上级路标**：[根目录 `LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/LANDMARKS.md)

本目录提供 Agent 在迁移循环中使用的原生进程内工具：只读工具 `read`、`grep` 以及唯一受守卫保护的写通道 `editandfixguard`。

---

## 一、下级路标导航（Child Landmarks）

* 📄 **[`inline_tools/editandfixguard/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/LANDMARKS.md)** — `edit()` 写通道与 `fix_guard` 守卫的 6 项代码缺陷修补与测试补齐指南

---

## 二、本目录实现现状核实

1. **已完整实现且无需改动的模块**：
   * [`_workspace.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/_workspace.py)：`resolve_project_root` 与 `resolve_workspace_path`（强制相对路径/`res://` 归一、防 `../` 与 symlink 逃逸、拦截 `.godot`/`.import`/`.codeindex`）。
   * [`read/__init__.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/read/__init__.py)：`read(project_root, path, line_from=1, line_to=None)`，返回 1-based 行号与逐字文本（上限 2000 行）。
   * [`grep/__init__.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/grep/__init__.py)：`grep(project_root, pattern=None, glob=None, path=None, context=0, max_results=100)`，底层安全调用 `rg`（`pattern=None` 时自动退化为 `rg --files` 列文件）。
   * [`tests/test_read.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/tests/test_read.py) 与 [`tests/test_grep.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/tests/test_grep.py)：共 19 个测试用例全部完备。
2. **存在代码断线需修补的子包**：
   * `editandfixguard/`：Step 1–10 的 9 个 Python 文件已落地，但存在顶层导出缺失、判据 5 未接线、落盘后场景复核误杀存量错误等 6 处问题，详见下级路标 [`inline_tools/editandfixguard/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/editandfixguard/LANDMARKS.md)。

---

## 三、本目录陈旧文档同步指南（Doc Sync Checklist）

本目录下的多份 `README.md` 与 `ARCHITECTURE.md` 仍停留在代码编写前的占位状态，需按以下清单同步更新：

- [ ] **更新 [`inline_tools/README.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/README.md)**：
  * 将标题「原生只读工具」修正为「迁移 Agent 的原生只读工具与受控写通道」。
  * 删除第 7、13 行「`editandfixguard` 目前只有文档和空包」的过时描述，改为已实现并通过 Step 1–10 验收。
  * 移除对不存在的 `docs/edit_and_fix_guard.md` 的死链引用。
- [ ] **更新 [`inline_tools/ARCHITECTURE.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/ARCHITECTURE.md)**：
  * 第 54–55 行修正说明：`codeindex` 现已通过场景旁路表（`scene_*`）索引 `.tscn`/`.tres`，但 `read` 和 `grep` 本身保持纯文本只读，不直接查询 `codeindex`。
- [ ] **更新 [`inline_tools/read/README.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/read/README.md) 与 [`inline_tools/read/ARCHITECTURE.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/read/ARCHITECTURE.md)**：
  * 删除「本目录目前只有文档，没有实现」与「断言未写」；在返回值示例中补齐 `"ok": true` 字段。
- [ ] **更新 [`inline_tools/grep/README.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/grep/README.md) 与 [`inline_tools/grep/ARCHITECTURE.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/grep/ARCHITECTURE.md)**：
  * 删除「没有实现」字样；在返回值示例中补齐 `"ok": true` 字段；在错误码表中补齐 `RG_NOT_FOUND` 与 `RG_FAILED`。
- [ ] **更新 [`inline_tools/tests/README.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/inline_tools/tests/README.md)**：
  * 删除「这里只有空文件，没有断言」，说明包含 19 个针对 `read` 与 `grep` 的完整回归测试。
