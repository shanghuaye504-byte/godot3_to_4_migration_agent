# `rag/build/` 编译产线路标文档 (LANDMARKS)

> **上级路标**：[`rag/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/LANDMARKS.md)  
> **下级路标**：*(当前为叶子节点，无下级路标文档)*

本目录包含将 `vault/` 原材料编译为 `artifacts/rules.db`（A 层）与 `artifacts/corpora/<id>/corpus.lance`（B 层）的全部脚本。

---

## 一、待修复的代码与测试路径错位

### 修复 1：统一类型 A `.prose.jsonl` 的落盘与读取路径
* **问题现状**：
  * [`parse_upgrading_docs.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/build/parse_upgrading_docs.py#L612) 第 612、639 行已将从官方 `.rst` 抽出的非表格散文写入子目录：
    `rag/vault/tier_b_prose/_raw/official_upgrading_guide/*.prose.jsonl`（磁盘上 8 个文件目前确实在此路径）。
  * 但以下 3 处代码仍硬编码查找旧路径 `rag/vault/tier_b_prose/*.prose.jsonl`：
    1. [`build_tier_a.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/build/build_tier_a.py#L324) 第 324 行（构建 `manifest.lock.json` 时漏锁了 `_raw/official_upgrading_guide/*.prose.jsonl`）。
    2. [`clean_prose_jsonl.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/build/clean_prose_jsonl.py#L15) 第 15 行（`PROSE_DIR = VAULT / "tier_b_prose"`）。
    3. [`rag/test/test_build_artifacts.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/test/test_build_artifacts.py#L18) 第 18、166 行（因在旧路径找不到 `.prose.jsonl` 而触发 `pytest.skip`）。
* **修改方案**：
  * 将 `build_tier_a.py`、`clean_prose_jsonl.py` 及 `rag/test/test_build_artifacts.py` 中的类型 A 散文路径统一指向 `vault/tier_b_prose/_raw/official_upgrading_guide/*.prose.jsonl`（或复用 `prose_preprocessing_util/chunker.py:type_a_paths()` 的兼容逻辑）。

### 修复 2：清理废弃的 `build_tier_b.py` 占位脚本
* **问题现状**：[`build_tier_b.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/build/build_tier_b.py) 仍是早期 `sys.exit(...)` 占位壳，真实 B 层构建已由 [`chunk_and_embed.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/build/chunk_and_embed.py)（调用 `chunk_prose.py` + `embed_prose.py`）完成。
* **修改方案**：让 `build_tier_b.py` 直接转发调用 `chunk_and_embed.main()`（或删除该 stub 并更新 `rag/README.md`）。

---

## 二、执行与文档同步 Checklist

- [ ] 修复 `build_tier_a.py`、`clean_prose_jsonl.py`、`rag/test/test_build_artifacts.py` 中的 `.prose.jsonl` 路径，确保 `test_prose_jsonl_present` 不再 skip 且测试通过。
- [ ] 将 `build_tier_b.py` 改为调用 `chunk_and_embed.main()`。
- [ ] 更新 [`rag/build/README.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/build/README.md) 与 [`rag/build/PARSING.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/build/PARSING.md)，移除「Parser 还没写」、「`build_all.sh` 目前还是空的」等历史备注。
