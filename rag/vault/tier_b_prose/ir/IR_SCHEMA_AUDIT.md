# E/F/G IR 与 Document IR schema 抽样核对

> 日期：2026-08-29。对照 [CHUNKING.md §3](../CHUNKING.md) 与 [`rag/build/prose_preprocessing_util/ir.py`](../../../build/prose_preprocessing_util/ir.py) 的 `ProseDocument` / `ProseBlock`。只抽查本轮 `compile_curation.py` 写出的 19 份 IR；ABCD 8 份只作字段一致性对照，未改动。

## 1. 方法

对 `ir/{community_blog,community_gist,github_pr,github_issue,github_discussion}/*.ir.json` 逐份：

1. `json.loads` 后 `ProseDocument.model_validate`（Pydantic）
2. 文档级字段集合 ≡ `{schema_version, doc_id, source, source_file, source_url, source_type, since_version, confidence, title, keep, match_tokens, blocks}`
3. 块级字段集合 ≡ `{block_id, type, text, heading_path, level, language, subtype}`
4. `source` / `source_type` / 所在桶三者对齐（CHUNKING §3.2 / §3.4）
5. `doc_id` 以 `source_type/` 开头；gist 拆分用 YAML stem，避免撞 id

结果：**19/19 通过 `model_validate`，0 条 schema 违规。** 无多余字段、无缺字段。

## 2. CHUNKING §3 对照表

### 2.1 文档级（抽全部 19 份）

| 字段 | 协议要求 | 本轮 IR |
| --- | --- | --- |
| `schema_version` | int，当前为 1 | 全部 `1` |
| `doc_id` | `<source_type>/<source_file>` | 博客/GitHub 为 `community_blog/….html`、`github_pr/….md` 等；**gist 拆分**为 `gist/wolfgangsenff_migration_notes.<topic>`（见 §4） |
| `source` | 见 §3.2 表 | F/G = `community_prose`；E = `github_pr` / `github_issue` / `github_discussion` |
| `source_file` | 原始文件名，不含路径 | 博客 `.html`；GitHub `.md`；gist 七份都指向 `wolfgangsenff_migration_notes.html` |
| `source_url` | 可选 | 全部为表 2.2 抓取 URL，非 null |
| `source_type` | §3.4 枚举 | `community_blog` / `gist` / `github_pr` / `github_issue` / `github_discussion`，均在枚举内 |
| `since_version` | 可选 | 全部 `"4.0"`（README 表 2.2 第 1–10 条同属 3→4） |
| `confidence` | 可选 | 全部 `needs_review`（CHUNKING §7.3） |
| `keep` | bool | 全部 `true` |
| `match_tokens` | list[string] | 全部非空，主题挂钩符号 |
| `blocks` | list[Block] | 1–5 块（人工摘录，远小于官方 rst 的上百块） |

### 2.2 块级（抽 3 份代表）

| 样本 | 观察 |
| --- | --- |
| [`community_blog/await-coroutine-basics.ir.json`](community_blog/await-coroutine-basics.ir.json) | `b0001` paragraph + `b0002` code（yield 对照），`b0003` paragraph + `b0004` code（`_process` 堆积）。`heading_path` 为 list。code 带 `language: gdscript`。无 `heading` 块（curation 编译器只产出 paragraph/code，符合 §7.3） |
| [`community_gist/wolfgangsenff_migration_notes.tweens.ir.json`](community_gist/wolfgangsenff_migration_notes.tweens.ir.json) | `doc_id=gist/wolfgangsenff_migration_notes.tweens`，`source_file` 仍是原始 html。1 paragraph + 1 code |
| [`github_pr/godot_pull_41794.ir.json`](github_pr/godot_pull_41794.ir.json) | 落在 `ir/github_pr/` 而不是 `community_blog/`。`source`/`source_type` 均为 `github_pr`。`heading_path` 为 `["body by KoBeWi"]`（opening post） |

块 `type` 仅出现 `paragraph` 和 `code`，都在 §3.3 枚举内。`level` / `subtype` 为 null（YAML 摘录没有 heading 层级或作者 subtype，合法可选字段）。

## 3. 桶映射（本轮要防的回归）

改映射前，未知 `source_type` 会 fallback 到 `community_blog`。抽查路径：

| IR 路径 | `source_type` | 是否错桶 |
| --- | --- | --- |
| `ir/community_blog/*.ir.json` × 7 | `community_blog` | 否 |
| `ir/community_gist/*.ir.json` × 7 | `gist` | 否 |
| `ir/github_pr/godot_pull_41794.ir.json` | `github_pr` | 否 |
| `ir/github_pr/godot_pull_65271.ir.json` | `github_pr` | 否 |
| `ir/github_issue/godot-docs_issue_5577.ir.json` | `github_issue` | 否 |
| `ir/github_issue/godot-docs_issue_6265.ir.json` | `github_issue` | 否 |
| `ir/github_discussion/godot-proposals_discussion_6192.ir.json` | `github_discussion` | 否 |

`community_blog/` 下没有 GitHub 文件。

## 4. 与协议的一处有意偏差

CHUNKING §3.2 写 `doc_id = <source_type>/<source_file>`。gist 七份 YAML 共用同一个 `source_file=wolfgangsenff_migration_notes.html`，若照抄会得到七个相同 `doc_id`，chunker 去重时会互相覆盖。

编译器因此在「YAML stem = 原始 stem + `.topic`」时用 stem 作为 `doc_id` 的文件分量，例如 `gist/wolfgangsenff_migration_notes.tweens`。`source_file` / `source_url` 仍指向原始快照，可追溯。博客和 GitHub 仍是规范的 `<source_type>/<source_file>`。

## 5. 与 ABCD 已有 IR 的字段一致性（不改它们）

BCD 8 份同样能 `model_validate`，字段集合相同。差异是 **取值约定**，不是 schema 裂开：

| | ABCD（官方 process 脚本） | EFG（curation 编译） |
| --- | --- | --- |
| `confidence` | `verified` | `needs_review`（§7.3） |
| `source_type` | `rst` / `html_sphinx` / `html_blog` | `community_blog` / `gist` / `github_*` |
| `source` | `official_doc` / `official_blog` | `community_prose` / `github_*` |
| `blocks[].type` | 含 heading / list / admonition | 仅 paragraph + code |
| 体量 | 数十到数百块 | 1–5 块 |

这是两条管线的设计差，不是 EFG 写错字段。BCD 里 `gdscript_basics.rst.ir.json` 的 `match_tokens` 很吵（docutils role 文本），与本次无关。

## 6. 抽样知识点是否还在

| 知识点 | 命中文件 | 文本抽查 |
| --- | --- | --- |
| `_process` 里每帧 await 堆积 | `await-coroutine-basics.ir.json` | 含 “huge pile” / `await get_tree().create_timer` |
| `$Tween` / `interpolate_property` | `fix-godot-tween-not-working-godot-4.ir.json` | 含 Nonexistent function、kill/re-create |
| `.rpc()` 无 `@rpc` 静默 | `fix-godot-rpc-call-not-working-enet-multiplayer.ir.json` | 含 “silently do nothing” |
| `move_and_slide` 阴影 `velocity` | `fix-godot-characterbody2d-….ir.json` | 含 shadows the built-in property |
| 类内部也走 setter | `godot-4-setter-getter.ir.json` | 含 “always get called” |
| Tween fire-and-forget | `github_pr/godot_pull_41794.ir.json` | 含 “fire and forget”、`create_tween` |
| `FileAccess.open` 静态、无 `close()` | `github_pr/godot_pull_65271.ir.json` | 含 “lack of a close() method” |
| extents 数值语义 | `…rectangleshape.ir.json` | 含 half the intended size |
| 必须 `super._ready()` | `…editorplugin.ir.json` | 含 “not called automatically” |

无 nav/footer、无 `+1`、无 C# diff、无 MCP 产品广告。

## 7. 结论

本轮 19 份 IR 与 CHUNKING.md §3 / `ProseDocument` 一致，GitHub 三桶路径正确。唯一需要记住的偏差是 gist 拆分的 `doc_id` 用 YAML stem。可以交给后续 `chunk_and_embed.py`；本次未跑切块或 embedding。
