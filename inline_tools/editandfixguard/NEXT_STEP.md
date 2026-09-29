# editandfixguard 实现顺序

功能以 `inline_tools/docs/edit_and_fix_guard.md` 为准。本文件是实现指导：每一项都是未完成的验收。上一步全部勾完，才做下一步。

验收命令：

```bash
uv run pytest inline_tools/editandfixguard/tests -q
```

涉及写盘的步骤还要断言：调用前后工作区字节一致，或 `git status --porcelain` 为空且没有新 commit。勾选表示对应测试已经通过，不要提前勾。

## 复用

- 路径：`inline_tools._workspace.resolve_workspace_path`。本目录再拒绝 `.git`、`*.uid`、`*.import`、白名单外后缀。
- 判据 5 的字面量：`inline_tools.grep`。glob 为 `*.tscn` 与 `*.tres`。
- 场景：`codeindex.scene.model.parse_scene`、`codeindex.scene.rules.check_scene`。
- 索引库：`codeindex.config` 的 `db_path`、`migration_rules_db`。只读 SQL 查 `scene_conn` 与 `scene_refs`。
- 同步：子进程 `codeindex sync <path>`。失败不回滚 commit。
- 符号：两边 error 节点都为 0 时才调用 `GdscriptParser.parse`。有 error 时只数节点。
- 规则库：只读 SQLite。表名用库里实际存在的 `migration_rules` 或 `rules`，列用 `id` 与 `old_symbol`。
- git 用 argv 列表，`shell=False`。不改 `GdscriptParser`、writer、verify、read、grep、场景解析。
- `inline_tools/ARCHITECTURE.md` 第 4 节仍写「codeindex 不索引 `.tscn`」。那句只约束 read/grep 自己不调用索引。判据 5 以设计书和本文件为准，场景旁路表已经存在。

## 文件在哪一步出现

不要在 Step 0 把业务文件一次建齐。每一步只新增自己的文件；上一步的文件保持可导入。

| 步骤 | 新增 |
| --- | --- |
| Step 0 | 已有：`README.md`、`NEXT_STEP.md`、`__init__.py`、`tests/README.md` |
| Step 1 | `precheck.py`、`tests/test_precheck.py` |
| Step 2 | `anchor.py`、`tests/test_anchor.py` |
| Step 3 | `guard.py`、`tests/test_guard_radius.py` |
| Step 4 | `symbols.py`、`rules_db.py`、`tests/test_guard_symbols.py` |
| Step 5–6 | 仍在 `guard.py`，测试按判据另开文件 |
| Step 7 | `scene_names.py`、`tests/test_guard_scene.py` |
| Step 8 | 仍在 `guard.py`，`tests/test_guard_verdict.py` |
| Step 9–10 | `edit.py`、`git_txn.py`、`sync_index.py`、`tests/test_edit_txn.py` |

Step 1 到 Step 8 的测试直接调用该步的函数，不经过尚未写完的 `edit()`。`edit()` 的编排只在 Step 9 接上。`__init__.py` 在对应函数落地时再导出，不要提前导出不存在的名字。

## 不许自行解释的约定

设计书没写死、但实现时必须按下面做，不要另选一种：

- 一次 `edit` 只改一个 `file`。`kind` 只有 `patch`、`create`、`revert`。模型可见字段只有设计书 schema 里的那些，没有行号，没有 `base_sha`。
- `context_before` / `context_after` 各 0～3 行。超过 3 行返回 `CONTEXT_TOO_LONG`，不写盘。
- 扩展名只认白名单。白名单外（含通常的二进制后缀）一律 `PATH_FORBIDDEN`。另用 NUL 字节走 `NOT_TEXT`，不再做第二张扩展名表。
- 根因的 `line` 为 `None` 时，这条根因不提供距离。该文件不能因此整份放行，除非它同时是 pointer 的 `target_res_path` 或出现在 `declared_scope`。
- `FUZZY_ANCHOR` 不拒绝。它进入返回值的 warnings；若没有 block，最终 `verdict` 至少是 `warn`。
- 判据 3 的 `added` / `removed` 不计 `+++` 和 `---` 行。
- error 节点包含 tree-sitter 的 `is_error` 与 `is_missing`，与 `root.has_error` 的范围一致。两边只要有一边计数大于 0，就不做符号集合差。`new` 的计数不大于 `old` 时，G2.1 也不拒绝。
- 判据 5 查 `scene_refs` 时 kind 只限 `conn_signal`、`conn_method`、`node_type`、`res_type`、`script_class`，再加 `scene_conn.signal` 与 `scene_conn.method`。索引库不存在时只跑 `grep`，不因此拒绝。
- `git apply` 的补丁写在工作区之外的临时文件。commit 带 `--no-verify`。`justification` 不进入 argv。
- `counts_as_verify_round`：`reject` 为 false；`pass` 和 `warn` 为 true。成功且 sync 成功时 `index_stale` 为 false。
- `codeindex sync` 使用安装后的 `codeindex` 命令（根环境的 path 依赖），参数是该文件的路径。不在本目录重写 `reindex_batch`。
- commit 失败的错误码是 `COMMIT_FAILED`，并按 Step 9 回滚。

## Step 0 骨架

- [x] `inline_tools.editandfixguard` 可导入。本步不要求 `edit.py` 等业务文件已经存在
- [x] 根 `pyproject.toml` 有 tree-sitter、language-pack、codeindex path 依赖；本目录没有 `pyproject.toml`；根 `uv.lock` 与这份依赖一致
- [x] README 写明宿主注入参数，以及设计书 1.8 的不做清单

## Step 1 第 0 步前置

- [x] 非 git 仓库 → `NOT_A_GIT_REPO`，不执行 `git init`
- [x] `git status --porcelain` 非空 → `DIRTY_WORKTREE`，不写盘
- [x] `../`、绝对路径、symlink 穿出 → `PATH_ESCAPE`
- [x] `.godot/`、`.import/`、`.codeindex/`、`.git/`、`*.uid`、`*.import`、二进制后缀、白名单外后缀 → `PATH_FORBIDDEN`
- [x] 白名单仅 `.gd .tscn .tres .gdshader .godot .cfg`
- [x] NUL、大于 4MB、非 UTF-8 → `NOT_TEXT`
- [x] 通过时记下 `HEAD` sha；以上失败磁盘字节不变

## Step 2 锚定与规范 diff（第 1–4 步）

- [x] `needle = context_before + remove + context_after`；命中 1 次得到 1-based 行号
- [x] 命中多于 1 次 → `AMBIGUOUS_ANCHOR`，附全部候选行号，不写盘
- [x] 精确失败后做行尾空白、CRLF→LF、tab/space 归一化
- [x] `context_before` 或 `context_after` 超过 3 行 → `CONTEXT_TOO_LONG`，不写盘
- [x] `FUZZY_ANCHOR` 不拒绝；无 block 时最终 `verdict` 至少为 `warn`
- [x] 仍失败则 `SequenceMatcher` ratio > 0.92 接受并带 `FUZZY_ANCHOR`；否则 `ANCHOR_NOT_FOUND`，附最相似的 3 个片段和真实行号
- [x] 多个 hunk 行区间交叠 → `OVERLAPPING_HUNKS`
- [x] 替换从后往前，避免行号漂移
- [x] `new_text` 与 `old_text` 字节相同 → `EMPTY_EDIT`
- [x] `difflib.unified_diff(..., n=3)` 的 hunk 头是 1-based；不用 `verify_shell.diff.DiffView` 取行号
- [x] 本步不写盘

## Step 3 判据 1 爆炸半径

- [x] `C` = 根因 `(res_path, line)` ∪ `pointers[].target_res_path` ∪ `declared_scope`
- [x] 根因文件上 `|行差| > 15` 拒绝；`N = 15`
- [x] 根因 `line` 为 `None` 时，不把该文件整份放行
- [x] pointer 的目标文件任意行通过；其 `res_path`（引用方）不因此进入 `C`
- [x] 行号与 verify 的 `line` 同为 1-based，不读 `symbols.line`
- [x] `rule_id` 在规则库中存在时，允许改该行 `old_symbol` 的出现位置；id 不存在或库打不开则豁免不生效
- [x] `declared_scope` 的文件路径让该文件整份进入 `C`；`res://player.gd#func:名字` 至少让该文件进入 `C`

## Step 4 判据 2、G2.1、G5.1

- [x] 在内存中跑 tree-sitter，不调用 writer，不写 `index.db`
- [x] 两边 error 节点数都为 0 才做 `S_before − S_after`；计数含 `is_error` 与 `is_missing`；kind 为 class/func/signal/var/const/enum
- [x] 注释和字符串里的 `func` 不算符号
- [x] 消失的符号未在 `declared_scope` 逐个列出 → 拒绝
- [x] `new` 的 error 节点数大于 `old` → `SYNTAX_REGRESSION`，不报符号消失
- [x] `create` 时 `old_text` 为空，判据 2 不触发
- [x] `S_after − S_before` 的名字落在 `old_symbol` 列 → `REVERSE_MIGRATION`；旧文本里已有的旧符号不因此失败
- [x] 规则库打不开 → `RULES_DB_UNAVAILABLE` 且本检查拒绝
- [x] 不修改 `GdscriptParser` 的 `has_error` 抛异常约定

## Step 5 判据 3

- [x] `removed - added > 10` 且 `added < removed * 0.3` → warn，不 block；`added` / `removed` 不计 `+++` 与 `---`
- [x] 删除行数 `> max(30, 文件行数的 40%)` 且未设 `allow_bulk_delete` → `BULK_DELETE`
- [x] `allow_bulk_delete=True` 只豁免 G4.1，比值 warn 仍在，并记入 override
- [x] `new_text` 为空或字节数 `< old_text 的 10%` → `FILE_TRUNCATED`，无豁免

## Step 6 判据 4

- [x] 只扫 udiff 的 `+` 行
- [x] 整行 `pass` → block
- [x] `# TODO` / `FIXME` / `XXX` / `HACK` 与 `# ...` → warn
- [x] 注释含 `original`、`unchanged`、`as before`、`其余`、`不变` → block
- [x] `push_error` 引号内匹配 `not implement` → block
- [x] `-` 行 strip 后等于 `+` 行去掉一个前导 `#` 再 strip → `COMMENTED_OUT`，block
- [x] 无 override；文件里原有的 `pass` 不算

## Step 7 场景不变量与判据 5

- [x] `.tscn`/`.tres`：post 的 `P_*` 真包含 pre → `SCENE_SYNTAX_REGRESSION`
- [x] post 新出现 `<<<<<<<` / `=======` / `>>>>>>>` 而 pre 没有 → `CONFLICT_MARKER`
- [x] post 的 L4 ERROR 指纹真包含 pre → `SCENE_INVARIANT_REGRESSION`；弃权项不计入
- [x] `create` 时 pre 为空，新文件自身的 error、`P_*`、L4 ERROR 视为回归
- [x] `.gd` 上 class/func/signal 改名（不是纯删除）时，查 `scene_conn.signal` / `method`，以及 `scene_refs.symbol` 且 kind 仅为 `conn_signal`、`conn_method`、`node_type`、`res_type`、`script_class`
- [x] 索引库不存在时只跑 `grep`，不因此拒绝
- [x] 旁路表未覆盖的字面量再调用 `inline_tools.grep`，词边界，glob 为 `*.tscn` 与 `*.tres`
- [x] 命中 → `INCONSISTENT_RENAME`，warn，附路径和行号，不 block
- [x] 不把 `.tscn` 送进 tree-sitter，不把场景边写入 `symbols`

## Step 8 裁决

- [x] 任一 block 未被其 override 接住 → `reject`；只有 warn → `warn`；否则 `pass`
- [x] reject 时同一次调用里的 warn 仍出现在 `violations`
- [x] `violations` 含 `id`、`file`、`line`、`message`；锚点失败另附候选片段
- [x] override 进入返回 JSON
- [x] `reject` 时 `counts_as_verify_round` 为 false；`pass` 与 `warn` 时为 true

## Step 9 git 事务、create、revert、sync

- [x] `git apply --check` 失败 → `APPLY_CHECK_FAILED`，磁盘未动
- [x] `git apply --index`；命令行不含 `--reject`、不含 `--3way`；补丁文件在工作区之外
- [x] commit 使用 `--no-verify`；失败 → `COMMIT_FAILED`，并回滚到调用前 sha
- [x] 落盘后读回的字节必须等于内存 `new_text`；`.gd` 的 error 节点数不得高于内存判定；`.tscn`/`.tres` 再跑 `check_scene`。失败 → `SYNTAX_BROKEN` 或 `SCENE_REGRESSION`，并 `reset --hard` 到调用前 sha
- [x] 第 6 步之后的失败都执行 `git reset --hard <base_sha>` 与 `git clean -fd -e .godot -e .import -e .codeindex`，且不含 `-x`
- [x] commit message 含 `round`、文件、`sig-before`、`sig-after`、`rule-id`、`guard`、`patch-hash`；无 verify 时 signature 为 `none`；warn 的 override id 写进正文
- [x] message 由服务端拼接，不把 `justification` 送进 shell
- [x] `codeindex sync` 失败不 reset，返回 `index_stale=true`
- [x] `kind=create`：`content` 为 `new_text`，无锚定；commit 失败后 untracked 新文件被 clean 掉
- [x] `kind=revert`：不跑写前判据；`to_commit is None` 时退到 `HEAD~1`；有 `baseline_sha` 时拒绝退到 baseline 之前；未传入 baseline 时只允许退一个 commit；回滚后对受影响文件 sync
- [x] 不调用 `git stash`、`git worktree`、`git init`、`git config`；不 wipe `*.uid`；不写 `.gitignore`
- [x] 返回字典含 `ok`、`commit`、`guard`、`applied_files`、`reject_reason`、`index_stale`、`counts_as_verify_round`
- [x] guard 拒绝、锚点失败、前置失败时，工作区字节与调用前一致，且没有新 commit

## Step 10 串起来

- [x] 一次合法 `patch`：commit 出现，工作区 clean，message 字段齐全，`verdict=pass`
- [x] 一次判据 4 拒绝：无 commit，文件字节不变，`counts_as_verify_round=false`
- [x] 一次 warn（判据 5 或 TODO）：有 commit，`verdict=warn`，violations 与 override 都在返回值和 message 里
