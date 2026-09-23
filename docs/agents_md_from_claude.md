# CLAUDE.md → AGENTS.md 复制记录

日期：2026-09-21

## 扫描结果

全仓库只找到一份协作指令文件：根目录 `CLAUDE.md`。`rag/`、`codebase_index/`、`inline_tools/`、`godot_test/` 等子模块没有自己的 `CLAUDE.md`，因此没有生成嵌套 `AGENTS.md`。

未扫描 `.gitignore` 中的独立目录（`godot_rag/`、`godot_test/clean_control*`、`working_notebook/`）。

## Codex 格式差异（相对原文件）

Codex 读取 `AGENTS.md`（及同目录 `AGENTS.override.md`），按「仓库根 → 当前工作目录」串联，更深文件覆盖更浅文件；默认合计上限 `project_doc_max_bytes` = 32 KiB。本仓库根文件约 21 KiB，无需拆分。

相对 `CLAUDE.md` 的适配：

1. 文件名改为 `AGENTS.md`，文首增加 Codex 作用域说明。
2. Claude Code 的 `@ARCHITECTURE.md` 引用改为普通路径 `` `ARCHITECTURE.md` ``。
3. 模板占位符 `{{PROJECT_NAME}}`、`{{DESIGN_NOTES_FILE}}` 落实为 `godot3_to_4_migration_agent` 与 `DESIGN_NOTES.md`。
4. 正文其余部分保持与 `CLAUDE.md` 一致；`CLAUDE.md` 仍保留给 Claude Code。

两份文件之后若改协作规则，需要同步更新。
