# 评测集生成记录

本文件记录 `eval/test_tier_a/` 与 `eval/test_tier_b/` 的生成策略、随机种子与过滤条件，供后续复现与审计。

## 生成脚本

```bash
cd rag
# A/B 层 queries 都已人工正向对齐。再跑会冲掉两边的 jsonl。
# uv run python eval/build_eval_set.py
```

可选参数（仅当你明确要重抽骨架时）：

```bash
uv run python eval/build_eval_set.py --target-version 4.7.1 --seed 42 --out eval/
```

**禁止**用该脚本覆盖 `eval/test_tier_a/` 与 `eval/test_tier_b/` 的现行 queries。见下方「A 层正向改写」与「B 层正向改写」。

## 随机种子

固定种子 `42`（A 层）/ `43`（B 层，代码里用 `seed + 1`），保证每次生成结果一致。

## A 层抽样策略

数据源：`artifacts/rules.db` 的 `migration_rules` 表。

过滤条件：

- `detection_method IN ('agent_retrieval', 'agent_retrieval_or_escalate')`
- `old_symbol IS NOT NULL`
- `change IN ('rename', 'remove', 'signature', 'type', 'move', 'replace', 'behavior', 'rewrite')`

排除 `change='add'` 的规则，因为新增 API 没有"旧符号可报"，不适合做检索召回评测。

抽样后随机打乱，取：

- 前 10 条作为 `single`
- 后续约 70 条分成 20 组 `composite`

组合分组：按 `symbol_kind` 分组，保证同组规则类型一致。

## B 层抽样策略

数据源：`artifacts/corpora/default/corpus.lance` 的 `corpus` 表。

全表 317 条 chunks 随机打乱，取：

- 前 10 条作为 `single`
- 后续约 70 条分成 20 组 `composite`

组合分组：按 `source_file` 分组，保证同组 chunks 来源一致。

## 查询生成策略

### A 层查询（已废弃，仅作第一版记录）

第一版按 `symbol_kind` 套报错模板，并把 `old_symbol` **和** `new_symbol` 都放进 `symbols`。同名签名/类型变更也被写成「函数不存在」。该策略已由「A 层正向改写」替换。

### B 层查询（已废弃，仅作第一版记录）

第一版从 `heading_path` 末段或 `related_symbols` 抽 `{topic}`，套迁移模板，**没有读 `chunk.text`**。该策略已由「B 层正向改写」替换，不要再按此生成。

### 查询层隔离

- A 层查询固定 `retrieval_mode: exact_only`，只评估 A 层字典召回。
- B 层查询固定 `retrieval_mode: semantic_only`，只评估 B 层散文召回。

## 已知限制

- A 层第一版把 `new_symbol` 塞进 `symbols`，等于预告答案；同名签名变更被写成「函数不存在」。已用「A 层正向改写」覆盖。
- B 层第一版 query 只套 heading 末段，**没有读 chunk.text**，与正文不对齐；已用「B 层正向改写」覆盖。
- 组合样本原先按 `symbol_kind` / `source_file` 抽签，组内话题经常无关。A 层 GT 骨架未重抽。
- `extract_symbols()` 只认 `Nonexistent function '…'`、`Invalid get index '…'`、`Identifier "…" not found`、反引号。项目设置 / Too many arguments / `Invalid set index` / `Cannot find signal` 抠不出来。生产路径必须由 Agent 把旧符号放进 `symbols`。

## A 层正向改写（2026-08-31）

A 层 SQL 只吃 router 交出的 `symbols`，对 `old_symbol` / `new_symbol` / `owner` / `match_tokens` 做 `IN`（见 `rag/retriever/docs/tier-a.md`）。`error_text` / `query_text` **不进 SQL**。`symbols` 为空时才跑 `extract_symbols(error_text)`。

第一版的问题：

1. `symbols` 同时放新旧名，等于把答案预告给 `new_symbol` 挂钩。生产里 Agent 刚看到报错，手里只有旧名。
2. 同名签名/类型/迁移（`register_text_enter`、`byte_offset`、`Semaphore.post`）被写成 `Nonexistent function`，Godot 不会这么报。
3. `Tween` 被写成「不存在的函数」。

改写原则（不迎合 Recall）：

1. 保留 30 个 `gt_id` 与全部 GT items，不重抽、不删离群规则。
2. **20 条合成报错**：`error_text` 仿 `godot --headless --check-only` 的 `SCRIPT ERROR` / `WARNING`。`rename`/`remove` 用 `Nonexistent function` / `Identifier "…" not found`；同名 `signature` 用 `Too many arguments` / `Invalid argument`，不用「函数不存在」。
3. **10 条语义提问**：`query_text` 问这条规则实际在记的事（新参数、类型变更、Tween 整段重写、旧 API 现名）。优先挑「写成不存在函数会撒谎」的条目。
4. `symbols` **只放各 GT 的 `old_symbol`**，不放 `new_symbol`，不放泛化 `owner`（`Node` 会淹没 `LIMIT 8`）。
5. 全部仍是 `retrieval_mode: exact_only`。

**10 条语义提问**：`a_0000` `0005` `0006` `0007` `0011` `0018` `0020` `0021` `0024` `0029`

**20 条合成报错**：其余。

同名符号在 `top_k=8` 下会挤掉 GT（`Tween` 多条 API、`add_image` 多条签名、`advance`/`animation_finished`）。这是字典拥挤，不是评测集写错。不要靠塞 `new_symbol` 把 Recall 抬回去。

## B 层正向改写（2026-08-31）

第一版 Recall ~0.27 的主因是评测集：query 由 heading 模板反向生成（「migrate Blank lines / Introduction」），`symbols` 来自噪声 `related_symbols`（`weapon.gd`、`Tweens`、`RID` 整表重复）。

改写原则：

1. 保留 30 个 `gt_id`，不重抽库。
2. 组合样本只删**无法与组内多数话题写成同一句问句**的离群 chunk（空泛升级导语、风格指南空行 vs 物理弹跳、类型词典 vs RPC 等）。删完后部分组合变成 `single`。
3. **15 条合成报错**：`error_text` 用正文里的旧 API / 行为变化（如 `interpolate_property`、`KinematicBody2D`、`yield`、`auto_translate`），`symbols` 只留正文出现的符号。
4. **15 条语义提问**：`query_text` 问这篇散文实际在回答的问题（Rect2 有哪些字段、`match` 的 `when` guard、`#region` 怎么写），不硬套「How do I migrate {heading}」。
5. 全部仍是 `retrieval_mode: semantic_only`。

现行集合：30 条 `gt_id`，22 条 `single` + 8 条 `composite`，共 38 个 chunk。

**15 条合成报错**（`error_text`）：`b_0002` `0004` `0005` `0009` `0011` `0012` `0014` `0015` `0016` `0017` `0018` `0020` `0023` `0025` `0026`

**15 条语义提问**（`query_text`）：`b_0000` `0001` `0003` `0006` `0007` `0008` `0010` `0013` `0019` `0021` `0022` `0024` `0027` `0028` `0029`

组合里删掉、无法与组内多数写成同一句问句的离群 chunk（典型）：

| gt_id | 留下的话题 | 删掉的离群例子 |
| --- | --- | --- |
| b_0010 | CharacterBody2D 弹跳示例 | `const` 语法、空泛「4.1 行为变更」导语 |
| b_0011 | RenderingDevice enum | OpenXR 编辑器类型（另一条破坏性变更） |
| b_0012 | `master`/`puppet` → `@rpc` | CharacterBody2D 不要直接改 `position` |
| b_0013 | NodePath | 仅一句「支持可选静态类型」 |
| b_0014 | `connect` / Callable | 组内无关条目 |
| b_0015 | RectangleShape2D `extents`→`size` | `yield`/`await`（已由 b_0004 覆盖） |
| b_0016 | KinematicBody2D → CharacterBody2D | 组内无关条目 |
| b_0018 | File → FileAccess | 组内无关条目 |

留下的 8 条 composite 仍要求能共用一个问题（同一篇升级笔记的静默行为、同一语言特性簇如 annotation / class）。

`symbols` 只保留正文里出现的 1～4 个符号，不再抄 `related_symbols` 噪声表。

不要再执行 `uv run python eval/build_eval_set.py` 来刷新 B 层 jsonl，那会洗掉这次人工对齐。以后若再生 B 层数据，必须先读 `chunk.text` 再写 query。
