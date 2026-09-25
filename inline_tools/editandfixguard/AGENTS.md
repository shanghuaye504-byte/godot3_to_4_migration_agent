# editandfixguard — Codex 任务说明

本文件只管 `inline_tools/editandfixguard/`。与仓库根目录 `AGENTS.md` 冲突时，语言、文档和依赖规则仍以根文件为准。本文件只规定这一包怎么实现，不放宽那些规则。

## 任务从哪来

只做本目录 `NEXT_STEP.md` 里第一个尚未全部勾完的 Step。该步每一条验收都有测试并且测试通过之后，才把对应条目改成 `[x]`。不要提前勾。不要做后面的 Step。不要把业务文件一次建齐。

每一步新增哪些文件，写在 `NEXT_STEP.md` 的「文件在哪一步出现」。

## 文档权威

按这个顺序。后面的文件不能推翻前面的行为：

1. `inline_tools/docs/edit_and_fix_guard.md` — 行为依据。流水线、判据公式、豁免、裁决、git 事务以它为准。
2. `inline_tools/editandfixguard/NEXT_STEP.md` — 实现顺序、验收清单，以及「不许自行解释的约定」。设计书没写死的选择以这一节为准。
3. 本文件 — 动手前要读的代码、禁止改动的范围。

不要当作实现依据：

- `inline_tools/DESIGN_NOTES.md` 第 7 节的旧流水线、MCP 形态、扩展名列表。
- `PENDINGS.md` 里和设计书重复的长文。背景可以看，目录和步骤以 `NEXT_STEP.md` 为准。
- `inline_tools/docs/edit_guard_rewrite.md`。不要改成单锚点或 `os.replace`。
- `inline_tools/ARCHITECTURE.md` 第 4 节「codeindex 不索引 `.tscn`」。那句只说明 read/grep 不调用索引。场景旁路表已经存在。

## 动手前要检索的代码

先搜符号，再读命中的函数。不要把整个 `codebase_index` 或 `DESIGN_NOTES.md` 读进上下文。

每一步都要看：

- `inline_tools/_workspace.py`：`resolve_workspace_path`。本包在它之上再拒绝 `.git`、`*.uid`、`*.import`、白名单外后缀。不要放宽 read/grep 已有的禁止目录。
- `inline_tools/read/__init__.py`、`inline_tools/grep/__init__.py`：只调用，不改。判据 5 的字面量用 `grep`。

按步骤再看：

| 步骤 | 先读这些，不要改它们 |
| --- | --- |
| Step 1 | `_workspace.py` |
| Step 2 | 设计书第 1.3–1.4 节。不要用 `godot_mcp/verify_shell/diff.py` 的 `DiffView` 取行号 |
| Step 3 | `godot_mcp/src/godot_mcp/verify_filter/models.py` 里 `res_path` 与 `target_res_path` 的注释；`verify_gate/tool.py` 的 `_event_to_dict` |
| Step 4 | `index/src/codeindex/parsers/gdscript.py` 的 `has_error` 分支；`parsers/base.py` 的 `Symbol.kind`；`db/writer.py` 分支 5。不调用 writer，不写 `index.db` |
| Step 7 | `index/src/codeindex/scene/model.py` 的 `parse_scene`；`scene/rules.py` 的 `check_scene`；`scene/schema.sql` 的 `scene_conn`、`scene_refs` |
| Step 9 | `index/src/codeindex/cli.py` 的 `cmd_sync`；`index/src/codeindex/config.py` 的 `db_path`、`migration_rules_db` |

规则库只读。表名用库里实际存在的 `migration_rules` 或 `rules`，列用 `id` 与 `old_symbol`。场景校验今天只查 `symbol_kind='class'`，本包的 G5.1 不限 class。

## 禁止

- 不改 `inline_tools/read/`、`inline_tools/grep/`、`inline_tools/_workspace.py` 的既有行为。
- 不改 `GdscriptParser`、writer、verify、场景解析。
- 不新建 `pyproject.toml`。新依赖只加在仓库根，并且已经加过，不要再加一层。
- 不给模型 Bash、裸 git、Godot argv。
- 不 `git init`，不 wipe `*.uid`，不写 `.gitignore`，不创建 baseline，不调用 `git stash`、`git worktree`、`git config`。
- 不把 `.tscn` / `.tres` 送进 tree-sitter，不把场景边写入 `symbols`。
- 测试放在本目录 `tests/`，不要放进 `inline_tools/tests/`。
- 验收命令：`uv run pytest inline_tools/editandfixguard/tests -q`。写盘步骤还要断言工作区字节或 `git status --porcelain`。

## 找不到依据

设计书和 `NEXT_STEP.md` 都没有写的行为，停下来问，不要另选一种实现。
