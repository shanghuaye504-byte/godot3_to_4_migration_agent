# 发给 Codex 的逐步 prompt

一次只发下面的一块。发下一块之前，确认上一块在 `NEXT_STEP.md` 里已经全部勾成 `[x]`，并且 `uv run pytest inline_tools/editandfixguard/tests -q` 通过。

Codex 的工作目录是仓库根。每块 prompt 都要求它先读 `inline_tools/editandfixguard/AGENTS.md`。

---

## Step 0

```text
阅读并遵守 inline_tools/editandfixguard/AGENTS.md。
只处理 NEXT_STEP.md 的 Step 0，不要写 precheck、anchor、guard、git。

核对这三件事是否已经成立：
1. import inline_tools.editandfixguard 成功，且没有导出尚不存在的 edit / fix_guard。
2. 仓库根 pyproject.toml 含 tree-sitter、tree-sitter-language-pack、codeindex 的 path 依赖；editandfixguard 下没有 pyproject.toml；uv lock --check 通过。
3. editandfixguard/README.md 写了宿主注入参数和设计书 1.8 的不做清单。

三项都成立就只把 Step 0 的对应条目改成 [x]。缺哪项就只补哪项。不要勾选 Step 1 及以后。
完成后运行：uv run pytest inline_tools/tests -q
已有的 read/grep 测试必须仍然通过。
```

---

## Step 1

```text
阅读并遵守 inline_tools/editandfixguard/AGENTS.md。
只实现 NEXT_STEP.md 的 Step 1（流水线第 0 步前置）。先读设计书第 1.4 节第 0 步，以及「不许自行解释的约定」。检索 inline_tools/_workspace.py 的 resolve_workspace_path，复用它，不要改这个文件。

只新增 precheck.py 和 tests/test_precheck.py。测试直接调用前置函数，不写 edit()。

验收条目以 NEXT_STEP.md Step 1 的清单为准，每一条都要有测试：
NOT_A_GIT_REPO（且不执行 git init）、DIRTY_WORKTREE、PATH_ESCAPE、PATH_FORBIDDEN（含 .git、*.uid、*.import 和白名单外后缀）、白名单只有 .gd .tscn .tres .gdshader .godot .cfg、NOT_TEXT（NUL、大于 4MB、非 UTF-8）。失败时工作区字节不变。通过时返回 HEAD sha。

测试全部通过后，只把 Step 1 勾成 [x]。不要开始 Step 2。
命令：uv run pytest inline_tools/editandfixguard/tests/test_precheck.py inline_tools/tests -q
```

---

## Step 2

```text
阅读并遵守 inline_tools/editandfixguard/AGENTS.md。
只实现 NEXT_STEP.md 的 Step 2（锚定、内存替换、规范 unified diff）。先读设计书第 1.3 节和第 1.4 节第 1–4 步，以及「不许自行解释的约定」。不要使用 godot_mcp.verify_shell.diff.DiffView 取行号。

只新增 anchor.py 和 tests/test_anchor.py。测试直接调用锚定函数。本步不写盘、不调用 git apply。

必须覆盖：needle 唯一命中得到 1-based 行号；多次命中 AMBIGUOUS_ANCHOR 并附全部行号；精确失败后的行尾空白、CRLF→LF、tab/space 归一化；context 超过 3 行返回 CONTEXT_TOO_LONG；ratio > 0.92 的 FUZZY_ANCHOR 不拒绝；否则 ANCHOR_NOT_FOUND 并附最相似的 3 个片段和真实行号；hunk 行区间交叠 OVERLAPPING_HUNKS；从后往前替换；字节相同 EMPTY_EDIT；difflib.unified_diff n=3 的 hunk 头是 1-based。

测试通过后只勾选 Step 2。
命令：uv run pytest inline_tools/editandfixguard/tests -q
```

---

## Step 3

```text
阅读并遵守 inline_tools/editandfixguard/AGENTS.md。
只实现 NEXT_STEP.md 的 Step 3（判据 1 爆炸半径）。先读设计书第 2.2 节。检索 verify_filter/models.py 里 res_path 与 target_res_path 的区别，以及 verify_gate/tool.py 的 _event_to_dict。行号用 1-based，不要读 symbols.line。

只新增 guard.py 里判据 1 所需的函数，以及 tests/test_guard_radius.py。用 Step 2 产生的 udiff 行号做输入。不要在这一步实现判据 2–5。

必须覆盖：C = 根因 (res_path, line) ∪ pointers[].target_res_path ∪ declared_scope；根因文件上距离大于 15 拒绝；根因 line 为 None 时不把该文件整份放行；pointer 目标文件任意行通过，其 res_path 不进入 C；rule_id 在规则库存在时允许改该行 old_symbol 的出现位置，id 不存在或库打不开则豁免不生效；declared_scope 的文件路径使该文件整份进入 C；res://player.gd#func:名字 至少让该文件进入 C。

测试通过后只勾选 Step 3。
命令：uv run pytest inline_tools/editandfixguard/tests -q
```

---

## Step 4

```text
阅读并遵守 inline_tools/editandfixguard/AGENTS.md。
只实现 NEXT_STEP.md 的 Step 4（判据 2、G2.1、G5.1）。先读设计书第 2.3 节。检索 gdscript.py 的 has_error 分支和 writer.py 分支 5。不要修改 GdscriptParser，不要调用 writer，不要写 index.db。

新增 symbols.py、rules_db.py、tests/test_guard_symbols.py。两边 error 计数都为 0 时才可以调用 GdscriptParser.parse。计数包含 is_error 和 is_missing。

必须覆盖：kind 仅为 class/func/signal/var/const/enum；注释和字符串里的 func 不算符号；未在 declared_scope 列出的消失符号被拒绝；new 的 error 节点多于 old 时只报 SYNTAX_REGRESSION，不报符号消失；new 的计数不大于 old 且两边并非都为 0 时，判据 2 和 G2.1 都不拒绝；create 的空 old_text 不触发判据 2；新出现的名字落在 old_symbol 列则 REVERSE_MIGRATION，旧文本里已有的旧符号不算；规则库打不开则 RULES_DB_UNAVAILABLE 并拒绝。查询不限 symbol_kind=class。

测试通过后只勾选 Step 4。
命令：uv run pytest inline_tools/editandfixguard/tests -q
```

---

## Step 5

```text
阅读并遵守 inline_tools/editandfixguard/AGENTS.md。
只实现 NEXT_STEP.md 的 Step 5（判据 3，含 G4.1、G4.2）。先读设计书第 2.4 节。在已有 guard.py 里追加，不要新开判据 4。

新增 tests/test_guard_deletion.py。

必须覆盖：removed - added > 10 且 added < removed * 0.3 时 warn 而不 block；added/removed 不计 +++ 和 ---；删除行数 > max(30, 文件行数的 40%) 且未设置 allow_bulk_delete 时 BULK_DELETE；allow_bulk_delete=True 只豁免 G4.1，比值 warn 仍在并记入 override；new_text 为空或字节数 < old_text 的 10% 时 FILE_TRUNCATED，且没有豁免。

测试通过后只勾选 Step 5。
命令：uv run pytest inline_tools/editandfixguard/tests -q
```

---

## Step 6

```text
阅读并遵守 inline_tools/editandfixguard/AGENTS.md。
只实现 NEXT_STEP.md 的 Step 6（判据 4）。先读设计书第 2.5 节的正则和注释化比较。只扫 udiff 的 + 行。不要把设计书例子里的 return 0 或单独的 return 加成新规则。

在 guard.py 里追加。新增 tests/test_guard_lazy.py。

必须覆盖：整行 pass 为 block；TODO/FIXME/XXX/HACK 和以 # ... 开头为 warn；注释含 original、unchanged、as before、其余、不变为 block；push_error 引号内匹配 not implement 为 block；减行 strip 后等于加行去掉一个前导 # 再 strip 时 COMMENTED_OUT 为 block；本判据没有 override；文件里原有的 pass 因为不是 + 行而不算。

测试通过后只勾选 Step 6。
命令：uv run pytest inline_tools/editandfixguard/tests -q
```

---

## Step 7

```text
阅读并遵守 inline_tools/editandfixguard/AGENTS.md。
只实现 NEXT_STEP.md 的 Step 7（G2.2、G2.3、G3.1 和判据 5）。先读设计书第 2.6 和 2.7 节。检索 parse_scene、check_scene 和 scene/schema.sql。不要把 .tscn 送进 tree-sitter，不要改场景解析，不要把场景边写入 symbols。

新增 scene_names.py 和 tests/test_guard_scene.py。判据 5 调用已有的 inline_tools.grep，不要新写 rg 子进程。

必须覆盖：post 的 P_* 真包含 pre 时 SCENE_SYNTAX_REGRESSION；新出现的冲突标记 CONFLICT_MARKER；post 的 L4 ERROR 指纹真包含 pre 时 SCENE_INVARIANT_REGRESSION，弃权项不算；create 时 pre 为空，新文件自身的 error、P_*、L4 ERROR 视为回归；.gd 的 class/func/signal 改名（不是纯删除）时查 scene_conn 和限定 kind 的 scene_refs；索引库不存在时只跑 grep 且不拒绝；旁路表没覆盖到的字面量用 grep 词边界、glob 为 *.tscn 和 *.tres；命中为 INCONSISTENT_RENAME，warn，附路径和行号，不 block。

测试通过后只勾选 Step 7。
命令：uv run pytest inline_tools/editandfixguard/tests -q
```

---

## Step 8

```text
阅读并遵守 inline_tools/editandfixguard/AGENTS.md。
只实现 NEXT_STEP.md 的 Step 8（裁决）。先读设计书第 2.8 节的表和三条铁律。把已有判据的结果收成 pass、warn、reject。不要在这一步落盘。

新增 tests/test_guard_verdict.py。

必须覆盖：任一 block 未被其 override 接住则 reject；只有 warn 则 warn；否则 pass。reject 时同一调用里的 warn 仍在 violations 里。violations 含 id、file、line、message；锚点失败另附候选片段。override 进入返回 JSON。counts_as_verify_round 在 reject 时为 false，在 pass 和 warn 时为 true。FUZZY_ANCHOR 不单独构成 reject；没有 block 时 verdict 至少是 warn。

测试通过后只勾选 Step 8。
命令：uv run pytest inline_tools/editandfixguard/tests -q
```

---

## Step 9

```text
阅读并遵守 inline_tools/editandfixguard/AGENTS.md。
只实现 NEXT_STEP.md 的 Step 9（git 事务、create、revert、sync，以及 edit() 编排）。先读设计书第 1.4 节第 6–11 步、第 1.5–1.7 节。检索 cli.py 的 cmd_sync。git 使用 argv 列表，shell=False。

新增 edit.py、git_txn.py、sync_index.py、tests/test_edit_txn.py。用临时 git 仓库做测试，不要改本仓库的工作区。补丁写在被测工作区之外。commit 使用 --no-verify。codeindex sync 调用已安装的 codeindex 命令；测试里可以替换这个调用以模拟失败。

必须覆盖清单上的每一条：APPLY_CHECK_FAILED 时磁盘未动；apply 使用 --index 且不含 --reject 和 --3way；COMMIT_FAILED 会回滚；落盘后字节必须等于内存 new_text，.gd 的 error 节点不得高于内存判定，.tscn/.tres 再跑 check_scene，失败则 SYNTAX_BROKEN 或 SCENE_REGRESSION 并 reset --hard；第 6 步之后的失败都 reset --hard 再 git clean -fd -e .godot -e .import -e .codeindex，且不含 -x；commit message 字段齐全，无 verify 时 signature 为 none，warn 的 override id 在正文里，justification 不进 argv；sync 失败不 reset 且 index_stale 为 true，成功时为 false；create 无锚定，commit 失败后 untracked 新文件被清掉；revert 不跑写前判据，to_commit 为空时退到 HEAD~1，有 baseline_sha 时拒绝退到 baseline 之前，未传入时只允许退一个 commit，回滚后 sync；不调用 stash、worktree、init、config，不 wipe uid，不写 gitignore；返回字典字段齐全；guard 拒绝、锚点失败、前置失败时字节不变且没有新 commit。

测试通过后只勾选 Step 9。
命令：uv run pytest inline_tools/editandfixguard/tests -q
```

---

## Step 10

```text
阅读并遵守 inline_tools/editandfixguard/AGENTS.md。
只实现 NEXT_STEP.md 的 Step 10（三条端到端）。不要新加判据，不要改 read/grep/verify/parser。用临时 git 仓库。

在 tests/test_edit_txn.py 或 tests/test_edit_flow.py 里追加：

1. 一次合法 patch：出现 commit，工作区 clean，message 含 round、文件、sig-before、sig-after、rule-id、guard、patch-hash，verdict 为 pass。
2. 一次判据 4 拒绝（注释化或整行 pass）：没有 commit，文件字节不变，counts_as_verify_round 为 false。
3. 一次 warn（TODO 或 INCONSISTENT_RENAME）：有 commit，verdict 为 warn，violations 与 override 同时出现在返回值和 commit message 里。

三条都通过后只勾选 Step 10。
命令：uv run pytest inline_tools/editandfixguard/tests inline_tools/tests -q
后一条确认 read/grep 仍然通过。
```
