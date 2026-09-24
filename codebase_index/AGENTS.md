# codebase_index — 场景解析任务说明

本文件只管 `codebase_index/` 及其子目录。与仓库根目录 `AGENTS.md` 冲突时，语言、文档和依赖规则仍以根文件为准。本文件只追加「如何完成场景解析与场景校验」，不放宽那些规则。

## 任务从哪来

只做 `NEXT_STEP.md` 第 7 节清单里的事。一次只做第一个未勾选的 Step。该步验收全部通过之后，才把该步勾成 `[x]`，并删掉该步对应的 `SCENE_INDEX_TODO`。骨架那一项已经勾过，不要重做，也不要提前勾选还没跑通测试的步骤。

## 写代码之前必读

按这个顺序读，读完再改：

1. `NEXT_STEP.md` 第 7 节里当前这一步的原文，包括它点名的新建文件、要改的已有文件和验收条目。
2. `scenecheckfixture/README.md` 里的「测试时怎样算通过」。预期以这份 README 为准，不要凭记忆重写。
3. 该步点名的源文件和测试文件。现在它们多半只有注释。

改已有文件之前，先搜索 `SCENE_INDEX_TODO(<该步 id>)`，只改标记所在的位置。标记格式和 id 对照表在 `NEXT_STEP.md` 第 7 节开头。

## 冲突时以谁为准

- 实现契约以 `NEXT_STEP.md` 为准。
- 仓库根目录的 `PENDINGS.md` 只作背景。不要按它文末的总表另开工具、另建目录或改已经否掉的方案。
- `inline_tools/DESIGN_NOTES.md` 的目录章已作废。场景解析放在 `index/src/codeindex/scene/`，不要放进 `inline_tools`。
- `index/README.md` 和 `design.md` 描述现有索引怎么工作。动手前以代码为准。文档和代码不一致时停下来问，不要猜。

## 禁止

- 不改 `godot_mcp`。
- 不改 GDScript parser。
- 不把场景边写入 `edges`，不把 `.tscn` / `.tres` 送进 tree-sitter，也不写入 `files` 表。
- 不新建 `pyproject.toml`。
- 不用 Godot `ResourceLoader.load` 来验收 `scenecheckfixture/` 里这 8 个孤立场景。它们旁边没有脚本和贴图。

## 怎么检索

先搜索符号名或 `SCENE_INDEX_TODO`，再读命中的函数，不要整文件通读当检索。夹具里某条写法应得到什么结果，打开 `scenecheckfixture/README.md` 对着那个 `.tscn` 核对。找不到依据就停下来问。
