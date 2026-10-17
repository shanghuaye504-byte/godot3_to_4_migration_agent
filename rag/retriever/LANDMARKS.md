# `rag/retriever/` 检索运行时路标文档 (LANDMARKS)

> **上级路标**：[`rag/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/LANDMARKS.md)  
> **下级路标**：*(当前为叶子节点，无下级路标文档)*

本目录是 Agent 运行时直接 `import` 的混合检索库（`retrieve_cached` / `retrieve` / `load`）。核心逻辑已全部实现，当前需完成 **2 项调优**以最大化 Agent 在真实迁移循环中的命中率。

---

## 一、待完成的 2 项代码与配置优化

### 优化 1：将离线评测锁定的最优超参回写至 `retriever.yaml`
* **问题现状**：
  * [`rag/eval/reports/eval_report.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/eval/reports/eval_report.md) 与 `SESSION_STATE.md` 已通过消融实验证明：B 层使用 `bm25.k=20, bm25.weight=0.3, vector.k=20, vector.weight=0.7, recall_k=20, rerank_k=3, reranker=identity` 时检索效果最优（`Prec_GT@3 = 0.9000, MRR@3 = 0.8722`）。
  * 但 [`rag/retriever/retriever.yaml`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/retriever/retriever.yaml) 仍停留在早期默认值（`bm25.k: 3, vector.k: 10, weight: 1.0:1.0, recall_k: 10`），仅因为 [`rag/test/test_retriever_config.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/test/test_retriever_config.py) 硬编码断言了旧默认值。
* **修改方案**：
  1. 更新 [`rag/retriever/retriever.yaml`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/retriever/retriever.yaml) 的 `tier_b` 段：
     ```yaml
     tier_b:
       bm25:
         enabled: true
         k: 20
         weight: 0.3
       vector:
         enabled: true
         k: 20
         weight: 0.7
       rrf_k: 60
       recall_k: 20
       rerank_k: 3
       score_threshold: null
       reranker: identity
     ```
  2. 同步更新 [`rag/test/test_retriever_config.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/test/test_retriever_config.py) 中 `test_load_default_yaml` 的断言值。

---

### 优化 2：扩充 `router.py` 中 `extract_symbols()` 的报错提取正则
* **问题现状**：
  * [`rag/retriever/router.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/retriever/router.py#L46-L52) 中的 `_SYMBOL_PATTERNS` 目前仅匹配 4 种句式（`Nonexistent function`、`Invalid get index`、`Identifier "..." not found`、反引号）。
  * 当 Agent 仅传入 `error_text` 而未显式传 `symbols` 时，面对 Godot 4 常见的 `Invalid set index 'extents'`、`Cannot find member "foo" in base "Bar"`、`Function "instance" not found in base`、`Class "KinematicBody2D" hides a global script class` 等报错会提取出空列表 `[]`，导致 A 层精确查表被跳过。
* **修改方案**：在 [`router.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/rag/retriever/router.py#L46-L52) 的 `_SYMBOL_PATTERNS` 中追加：
  ```python
  _SYMBOL_PATTERNS: tuple[re.Pattern[str], ...] = (
      re.compile(r"Nonexistent function '([^']+)'"),
      re.compile(r"Invalid (?:get|set) index '([^']+)'"),
      re.compile(r'Identifier "([^"]+)" not found'),
      re.compile(r'Function "([^"]+)" not found'),
      re.compile(r'Cannot find (?:member|signal|property) "([^"]+)"'),
      re.compile(r'Type "([^"]+)" not found'),
      re.compile(r'Class "([^"]+)"'),
      re.compile(r"`([^`]+)`"),
  )
  ```

---

## 二、执行与验收 Checklist

- [ ] 更新 `retriever.yaml` 与 `rag/test/test_retriever_config.py`。
- [ ] 扩充 `router.py:extract_symbols()` 正则，并在 `rag/test/test_retriever_router.py` 中补充新报错句式的提取单测。
- [ ] 在 `rag/` 下运行 `uv run pytest` 确保全部测试通过。
