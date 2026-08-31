# E/F/G 人工 curation 总结

> 日期：2026-08-29。本文件记录这次 HITL 筛查写了哪些 YAML、跑了哪些脚本、以及 gist 里 README 预期段落是否真实存在。协议仍以 [CHUNKING.md](../CHUNKING.md) 为准。

## 1. 结论：若干份 YAML，不是一份

按 CHUNKING.md §6.7–§7.2：

- 类型 F：每个社区源一份 `curation/<stem>.yaml`（7 份）
- 类型 G：gist 按主题拆成 `curation/<stem>.<topic>.yaml`（7 份）
- 类型 E：每个 GitHub 线程一份 YAML（5 份）

合计 **19** 份 YAML，编译出 **19** 份 `ir/<bucket>/*.ir.json`。

## 2. 筛查口径

对照 [README.md](../README.md) 表 2.2「补充源」和原则 4：只留 **行为差异 / 静默失败 / 设计动机**。

阅读顺序：

1. `rag/build/intermediate/prose_review_queue.jsonl`（启发式候选，约 460 行，含 GitHub + 社区；文本截到 500 字）
2. `after_preprocess/<bucket>/*.blocks.jsonl` 全文块
3. `_raw/` 快照（GitHub `.md`、gist HTML 评论区）

**丢掉的内容：** SEO 引言、塔防/对话教程步骤、`@export_*` 全家桶、rename 大表（A 层已覆盖）、GitHub Thanks / +1 / C# `BuildOutputView.cs` 修编译过程贴、Related Issues 外链。

**没有重跑** `scan_tier_b_raw.py`、`process_community.py`、`process_github.py`。后两个会 `append_queue`，会把已有 queue 再追加一遍。

## 3. 实际落盘的 YAML

### F · 社区博客（7）

| 文件 | 留下的知识点 |
| --- | --- |
| `await-coroutine-basics.yaml` | yield→await 对照；`_process` 里每帧 await 会堆积 |
| `fix-godot-tween-not-working-godot-4.yaml` | `$Tween` 失效、`interpolate_property` 报错、kill/re-create |
| `fix-godot-rpc-call-not-working-enet-multiplayer.yaml` | 没加 `@rpc` 时 `.rpc()` 静默丢弃 |
| `fix-godot-characterbody2d-move-and-slide-not-moving.yaml` | 不再吃参数；局部 `var velocity` 阴影导致静默不动 |
| `godot-4-setter-getter.yaml` | 类内部访问也会触发 setter（3 不会） |
| `fix-nonexistent-function-connecting-signals-godot.yaml` | 转换器在方法名来自变量时转不好 |
| `godot4-export-annotations.yaml` | 仅 `export`/`onready`/`tool` → `@` 注解；不灌变体目录 |

### G · gist 按主题拆（7）

`source_file` 一律 `wolfgangsenff_migration_notes.html`，`source_url` 指向原 gist。`doc_id` 用 YAML stem，避免七份 IR 撞同一个 `gist/wolfgangsenff_migration_notes.html`。

| 文件 | 主题 |
| --- | --- |
| `wolfgangsenff_migration_notes.tweens.yaml` | Tween 不再是节点 |
| `wolfgangsenff_migration_notes.characterbody.yaml` | `move_and_slide` 无参、靠 `velocity` |
| `wolfgangsenff_migration_notes.packed_array.yaml` | Packed* 改为按引用传递 |
| `wolfgangsenff_migration_notes.modulate_shader.yaml` | modulate 从后处理变成 shader 输入 |
| `wolfgangsenff_migration_notes.logical_tests.yaml` | `if object:` 不再当空值；`array.slice` 右端开区间 |
| `wolfgangsenff_migration_notes.rectangleshape.yaml` | `extents→size` 但数值仍是半宽高（见 §5） |
| `wolfgangsenff_migration_notes.editorplugin.yaml` | 父类 `_ready`/`_process` 必须手动 `super`（见 §5） |

gist 正文里的 **rename 大表整段丢弃**（`Node.raise`、`Pool*Array` 改名清单等，A 层已覆盖）。

### E · GitHub（5）

| 文件 | `source_type` | 留下的内容 |
| --- | --- | --- |
| `godot_pull_41794.yaml` | `github_pr` | opening post：fire-and-forget、不再是节点、`create_tween` |
| `godot_pull_65271.yaml` | `github_pr` | `open()` 变静态、没有 `close()` |
| `godot-docs_issue_5577.yaml` | `github_issue` | 旧 `connect` 报错原文 + Callable 正确写法 |
| `godot-docs_issue_6265.yaml` | `github_issue` | 确认 4.0 起 setget 移除（该 issue 几乎只有这一句） |
| `godot-proposals_discussion_6192.yaml` | `github_discussion` | OP 质疑 + dalexeev 官方回应（丢掉 Thanks） |

## 4. 运行的脚本与顺序

代码改动：[`rag/build/compile_curation.py`](../../../build/compile_curation.py)

- `_SOURCE_TYPE_TO_BUCKET` 补上 `github_pr` / `github_issue` / `github_discussion`（否则 GitHub YAML 会 fallback 写到 `ir/community_blog/`）
- gist 拆分用 YAML stem 生成唯一 `doc_id`

然后只跑了编译（不 scan、不 process、不 chunk、不 embed）：

```text
1. （只读）rg 搜 gist HTML：RectangleShape2D / extents / EditorPlugin / super._ready
2. 写入 19 份 curation/*.yaml
3. rag/.venv/bin/python rag/build/compile_curation.py
```

`compile_curation.py` stdout：

```text
  wrote ir/community_blog/await-coroutine-basics.ir.json (4 blocks)
  wrote ir/community_blog/fix-godot-characterbody2d-move-and-slide-not-moving.ir.json (2 blocks)
  wrote ir/community_blog/fix-godot-rpc-call-not-working-enet-multiplayer.ir.json (2 blocks)
  wrote ir/community_blog/fix-godot-tween-not-working-godot-4.ir.json (5 blocks)
  wrote ir/community_blog/fix-nonexistent-function-connecting-signals-godot.ir.json (3 blocks)
  wrote ir/community_blog/godot-4-setter-getter.ir.json (2 blocks)
  wrote ir/github_issue/godot-docs_issue_5577.ir.json (2 blocks)
  wrote ir/github_issue/godot-docs_issue_6265.ir.json (1 blocks)
  wrote ir/github_discussion/godot-proposals_discussion_6192.ir.json (2 blocks)
  wrote ir/community_blog/godot4-export-annotations.ir.json (2 blocks)
  wrote ir/github_pr/godot_pull_41794.ir.json (2 blocks)
  wrote ir/github_pr/godot_pull_65271.ir.json (1 blocks)
  wrote ir/community_gist/wolfgangsenff_migration_notes.characterbody.ir.json (2 blocks)
  wrote ir/community_gist/wolfgangsenff_migration_notes.editorplugin.ir.json (2 blocks)
  wrote ir/community_gist/wolfgangsenff_migration_notes.logical_tests.ir.json (2 blocks)
  wrote ir/community_gist/wolfgangsenff_migration_notes.modulate_shader.ir.json (1 blocks)
  wrote ir/community_gist/wolfgangsenff_migration_notes.packed_array.ir.json (1 blocks)
  wrote ir/community_gist/wolfgangsenff_migration_notes.rectangleshape.ir.json (1 blocks)
  wrote ir/community_gist/wolfgangsenff_migration_notes.tweens.ir.json (2 blocks)
compile_curation: 19 IR files
```

GitHub 五份都进了 `ir/github_{pr,issue,discussion}/`，没有误写入 `ir/community_blog/`。

## 5. gist 里 README 预期段落是否存在

`after_preprocess/community_gist/*.blocks.jsonl`（parser 只吃到 gist **正文**）里 **没有** `RectangleShape2D.extents` 和 `super._ready()`。

对 `_raw/community_gist/wolfgangsenff_migration_notes.html`（含 GitHub 评论区）做 `rg` 之后：

| README 预期 | 实际 |
| --- | --- |
| `RectangleShape2D.extents→size`，转换器改名但数值仍是半宽高 | **在 gist 评论**（约 HTML 第 3642 行），已写入 `.rectangleshape.yaml` |
| EditorPlugin 必须手动 `super._ready()` | **部分命中**：评论（约第 6225 行）写的是「父类 `_ready`/`_process` 不再自动调用，必须 `super._ready()`」。全文 **没有出现 `EditorPlugin` 这个词**。YAML 仍用 `.editorplugin.yaml` 文件名 + `match_tokens` 含 `EditorPlugin`，因为这就是 README 表 2.2 第 9 条要挂钩的静默失效；摘录正文保持评论原意，不编造 EditorPlugin 专属步骤 |

未把这条 extents 陷阱同步进 A 层 `known_traps.yaml`（本次范围停在 B 层 IR）。

## 6. 下一步（本次不做）

- 不跑 `chunk_and_embed.py`
- 不改 ABCD 已有 IR
- IR 与 schema 的抽样见同一次交付的 [`../ir/IR_SCHEMA_AUDIT.md`](../ir/IR_SCHEMA_AUDIT.md)
