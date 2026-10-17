# `rag/` 模块路标文档 (LANDMARKS)

> **上级路标**：[根目录 `LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/LANDMARKS.md)

本目录是 Godot 3→4.7.1 迁移知识库（A 层结构化 SQLite 规则库 `rules.db` + B 层散文混合检索库 `corpus.lance`）的构建与运行时检索组件。目前整体完成度已达 **98%**，仅需做少量配置回写、路径对齐与杂物清理。

---

## 一、下级路标导航（Child Landmarks）

* 📄 **[`rag/build/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/build/LANDMARKS.md)** — 编译产线 `.prose.jsonl` 路径对齐与废弃占位脚本清理指南
* 📄 **[`rag/retriever/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/retriever/LANDMARKS.md)** — 生产 `retriever.yaml` 最优超参同步与报错符号提取正则扩充指南

---

## 二、本目录实现现状核实

1. **已就绪且无需重建的编译产物（`rag/artifacts/`）**：
   * [`artifacts/rules.db`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/artifacts/rules.db)：SQLite（`schema_version="2"`，目标版本 `4.7.1`），`migration_rules` 表共 **8260 行**（`api_diff`: 6612，`official_renames`: 1101，`official_prose`: 444，`official_renames_skipped`: 84，`manual_rewrite`: 10，`manual_trap`: 5，`official_prose_3to4_shader`: 4）。
   * [`artifacts/agent_context/upgrading_to_godot_4.rst`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/artifacts/agent_context/upgrading_to_godot_4.rst)：供宿主系统提示词引用的官方总指南原文。
   * `artifacts/chunks/default/chunks.jsonl` 与 `artifacts/corpora/default/corpus.lance/`：共 **317 个 `ProseChunk`**（384 维 `BAAI/bge-small-en-v1.5` 向量 + LanceDB FTS 全文索引）。
2. **已完成的离线评测（`rag/eval/`）**：
   * [`eval/run_eval.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/eval/run_eval.py) 已在 30 条 A 层查询与 30 条 B 层查询上跑完消融实验，报告位于 [`eval/reports/eval_report.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/eval/reports/eval_report.md)。

---

## 三、本目录顶层清理与文档同步清单（Checklist）

- [ ] **删除误生成的空会话文件**：删除 `rag/:memory:.ses`（SQLite 内存连接误落盘的 0 字节文件）。
- [ ] **清理 `rag/eval/` 下的废弃占位脚本**：
  * 删除或标记废弃 [`rag/eval/gen_eval_set.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/eval/gen_eval_set.py) 与 [`rag/eval/run_ablation.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/eval/run_ablation.py)（二者仅抛 `NotImplementedError`，已被 [`build_eval_set.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/eval/build_eval_set.py) 与 [`run_eval.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/eval/run_eval.py) 取代）。
- [ ] **同步更新 [`rag/README.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/README.md)**：
  * 第 209–211 行依赖表：将 `pyyaml` 与 `fastembed` 列入 `[project.dependencies]`，`beautifulsoup4` 与 `trafilatura` 列入 `build` 组。
  * 第 61、132 行：将 `artifacts/corpus.lance/` 修正为 `artifacts/corpora/default/corpus.lance/`。
  * 第 81–91 行目录树：更新 `test/`（补齐 5 个 `test_retriever_*.py`）与 `eval/`（替换为 `build_eval_set.py` 与 `run_eval.py`）。
- [ ] **同步更新 [`rag/vault/tier_b_prose/CHECKPOINT.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/vault/tier_b_prose/CHECKPOINT.md)**：
  * 标注阶段 2/3（19 份 curation YAML 与 27 份 `.ir.json`）及阶段 4（317 chunks 与 `corpus.lance`）均已于 2026-08-29 全部完成。
