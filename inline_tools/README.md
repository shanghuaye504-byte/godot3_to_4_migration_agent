# inline_tools — 迁移 Agent 的原生工具

本目录是主 Agent **直接 import 的 Python 函数**。它不是子项目：没有 `pyproject.toml`，没有 `src/` 布局，也不再起一个 MCP server。

当前状态：**代码尚未开始**。本文只锁定「还要补什么、放在哪、谁调用、按什么顺序写」。函数内部的判定、误伤和探针写在同目录 `DESIGN_NOTES.md`（不进 Git）。

范围是 `PENDINGS.md` 文末的 P0 / P1。场景旁路表、load sweep、ClassDB / I7 不在本轮。

---

## 0. 已有代码怎么接

三块已经落地的能力留在原包，不搬进本目录，也不再包一层 MCP。

| 能力 | 位置 | 主 Agent 怎么用 |
| --- | --- | --- |
| `verify` | `codebase_index/godot_mcp` 的 `run_verify_tool` | 直接调这个函数。不新起第二个 MCP 进程 |
| 迁移规则检索 | `rag.retriever.retrieve_cached` | 注册工具时只暴露 `error_text` / `symbols` / `query_text` / `kinds`。`target_version`、`top_k`、`retrieval_mode` 由配置注入 |
| 符号索引 | `codebase_index/index` 的 daemon、CLI、`queries`、`writer` | 查询走 `queries` + `connect_ro`。写完文件走 `writer.reindex_batch` |

`codebase_index/design.md` 里「Layer 1 / Layer 2 交给模型用 Bash 调 `rg` 和 `codeindex`」**不再执行**。模型没有 Bash，也看不到 argv。CLI 留给人和宿主排障；模型只调用本目录的函数。

允许改已有包的只有两处，而且都要先于依赖它们的工具：

| 编号 | 改哪里 | 做什么 | 不做什么 |
| --- | --- | --- | --- |
| F1 | `codebase_index/index` 的 `parsers/gdscript.py` | 增加只读函数，返回类型出现的字节区间（`type` 节点，含 `extends`） | 不改 CLI、不改 `schema.sql`、不改 `ParseResult` 字段 |
| F2 | `rag/retriever/tier_a.py`，并由 `rag/retriever/__init__.py` 导出 | `list_mechanical_renames(target_version)`：在现有检索死门上再收紧 | 不改 `RetrievalQuery`。本目录不写 SQL |

F2 的收紧条件（与 `query_rules` 同一套版本比较，只认 `since_version_code <= target`）：

```text
detection_method ∈ {agent_retrieval, agent_retrieval_or_escalate}
AND agent_action = apply_rename
AND symbol_kind ∈ {class, builtin}
AND old_symbol、new_symbol 均非空
```

`apply_and_warn` 不进这个函数。那些行是检索提示（转换器自己注释掉的改名、API 签名变化、`yield` / `Tween` 这类要重排语句的改写），不是可以盲替的对照表。

机械替换的第一刀只动**类型出现的位置**：GDScript 的 `type` 节点，以及 `.tscn` / `.tres` 的 `type=`。方法、属性、信号、项目设置、shader 改名继续只走检索，交给模型。原因和字段来源见 `DESIGN_NOTES.md`。

---

## 1. 目录

仓库根是 import 根。依赖记在将来的主 Agent 工程里（path 依赖 `codeindex`、`rag`、`godot_mcp`），不在这里再导出一个包。

```text
inline_tools/
├── README.md                 # 本文件
├── DESIGN_NOTES.md           # 实施指导（gitignore）
├── __init__.py
├── workspace.py              # 路径约束。不是工具，各工具共用
├── read/
├── grep/                     # pattern 为空时按 glob 列文件
├── edit/                     # 唯一写通道。内含 fix_guard 和符号比对
├── index_query/              # 只读符号查询。文件夹名避开 codeindex 包名
├── scene/                    # tscn_parse.py + scene_check.py
├── codemod/                  # rule_codemod
├── traps/                    # trap_scan
└── intake/                   # session_intake
```

不建 `gd_symbols/`：符号比对是 `edit/` 里对已有 `GdscriptParser.parse()` 的薄封装。不建 `trace/`，LangGraph 图也不放在这里。`.tscn` 不并进 codeindex：现有 registry 不认这个后缀，writer 会直接跳过。

```text
主 Agent（LangGraph，尚未建包）
  ├─ godot_mcp.run_verify_tool
  ├─ rag.retriever.retrieve_cached
  └─ inline_tools.*
        ├─ 读：read / grep / index_query
        ├─ 写：edit → 一次 reindex_batch
        └─ 宿主：intake / codemod / scene_check / trap_scan
              codemod、scene_check 读 F2
              codemod 读 F1 的类型坐标
```

`edit` 不 import `godot_mcp`。本轮根因的 `res_path` 和 `line` 由编排方作为参数传入。

---

## 2. 实现顺序

排在前面的模块**不得 import** 排在后面的模块。同一序号里的两项可以并行。

运行时还有一条和 import 无关的约束：`index_query` 可以先写完，但要查到刚改过的符号，必须等这次 `edit` 末尾的那一次 `reindex_batch` 返回。

| 序 | 位置 | 依赖 |
| --- | --- | --- |
| 1 | `workspace.py` | 无 |
| 2 | `read/`、`grep/` | 1 |
| 3 | `edit/`（guard 判据 1、2、注释化；成功后一次 `reindex_batch`） | 1，以及已有的 parser / writer |
| 4 | `index_query/` | 1，以及已有的 `queries`。与第 3 步无 import 关系 |
| 5 | F1 类型坐标；F2 `list_mechanical_renames` | 无互相依赖。都在已有包里 |
| 6 | `scene/tscn_parse.py` | 无。可与 2–4 并行写，但必须早于 8 和 9 |
| 7 | `intake/` | 子进程拉起 daemon，等到 `.codeindex/ready`。留下转换前快照 |
| 8 | `codemod/` | 3、5、6。落盘只走 `edit` |
| 9 | `scene/scene_check.py` | 6 和 F2。先做探针，再写「verify 看不见」的断言 |
| 10 | `traps/` | 7 的前后快照。只写报告，不调用 `edit` |

指标库、LangGraph checkpointer、OpenTelemetry 排在这 10 步之后。边界写在 `DESIGN_NOTES.md`，现在不建目录。

---

## 3. 模型可见的函数

工作区根来自 `config.yaml` / `CODEBASE_PROJECT_ROOT`，不出现在参数里。模型不能选工作区，不能拼命令行。

### 3.1 `read`

```text
read(slices: [{path, line_from, line_to?}])
  → {slices: [{path, lines: [{n, text}], total_lines, truncated}]}
```

一次可读多段。返回绝对行号，给 `edit` 做锚。路径相对 `project_root`，禁止逃出工作区，禁止读 `.godot/`、`.import/`、`.codeindex/`。

### 3.2 `grep`（含列文件）

```text
grep(pattern?, glob?, context?=0, max_results?=100)
  → {matches: [{path, line?, text?}], total_matches, truncated, files_only}
```

`pattern` 为空时按 `glob` 列文件，`files_only=true`，不再单开 glob 工具。纯 Python 遍历，遵守 `.gitignore`，排除上述三个运行时目录。不调用 `rg` 二进制。这是模型看见 `.tscn` / `.tres` / `.gdshader` 的通道；codeindex 不索引这些后缀。

### 3.3 `index_query`

```text
index_query(kind: "find_symbol" | "call_chain" | "class_hierarchy",
            name, depth?=3)
  → queries 的原有结构，或 {ready: false, reason}
```

直接 `import codeindex.db.queries` 和 `connect_ro`。daemon 未就绪时返回 `ready: false`，不把空结果说成「符号不存在」。

禁止模型调用 `up` / `status` / `down` / `sync`。也禁止在进程内调用 `codeindex.cli` 的 `cmd_*`：那些函数会 `sys.exit`，并把 JSON 打到 stdout。

### 3.4 `edit`（唯一写通道）

```text
edit(ops: [{file, hunks: [{context_before, remove, add, context_after}],
            content?}],
     declared_scope?, justification?, rule_id?)
  → {ok, commit, guard: {verdict, violations[]}, applied_files[], reject_reason}

edit_revert(to_commit?)
  → {ok, commit}
```

一次调用承接模型这一轮的全部 hunk，可以跨文件。hunk 不带行号，用上下文锚定。

落盘前在内存里做完：锚定、同一文件区间不得重叠、整批 guard。任一条 block 级判据失败，则整批不写盘、不提交、不计入 verify 轮次，把逐文件 `violations` 退回。

通过之后：用 `pathlib` 写入已经构造好的新文本，**一笔** `git add` 和 **一笔** commit，然后对 `applied_files` 调用一次 `reindex_batch`（`synced_by="sync_cmd"`，用完关闭连接）。不重启 daemon。git 参数由代码组装，模型看不到命令。

`rule_codemod` 走同一条 `edit`。机械批次允许丢掉 guard 未通过的文件，其余仍是一笔 commit，报告里列出跳过项。

单文件回退是 `checkout <parent> -- path` 再补一笔提交，不事先拆成每个文件一个 commit。

### 3.5 检索不在本目录

模型侧工具名仍叫 `retrieve_migration_rule`，实现就是 `rag.retriever.retrieve_cached`。本目录不包装它。

循环里的用法（编排方的事，不是新参数）：

- `coverage=rule_hit` 且 `recommended_action=apply_rename`，并且 `symbol_kind` 是 `class` 或 `builtin`：交给 `rule_codemod`。
- 其他 `apply_rename`（方法、属性、信号等）：模型通道，不要机械替换。
- `apply_and_warn` / `prose_only` / `no_hit`：模型通道。`no_hit` 且规则标明必须升级时，编排方结束循环，不让模型猜。

---

## 4. 宿主环节

这些函数由编排方调用。`scene_check` 可以另注册一个只能传 `scope="changed"` 的入口给模型自查；全量扫描的参数不交给模型，避免它跳过收尾或改 baseline。其余函数模型不可见。

### 4.1 `session_intake` — 会话开始，恰好一次

和 `verify` 内部的 `phase=intake` 不是同一件事。verify 那一步已经会清 `*.uid`、按需重建导入缓存、拍源码快照，不要外提。

本函数在调用 verify 之前做：把仓库放进隔离目录、记下转换前树（给陷阱对比）、`--convert-3to4`、扫被静默跳过的大文件（`>4MB` 或 `>100k` 行）、baseline commit、设置 `CODEBASE_PROJECT_ROOT`、子进程拉起 `python -m codeindex.daemon` 并等到 `ready`。产出 `intake_report.json`。

### 4.2 `rule_codemod` — 转换器之后、模型之前

```text
rule_codemod(mode: "plan" | "apply")
  → {plan[], conflicts[], skipped[], applied}
```

规则清单只来自 F2。替换位置只来自 F1 的类型坐标和 `tscn_parse` 的 `type=`。同一位点被两条规则命中则记入 `conflicts`，该位点不改。`apply` 必须走 `edit`，并带上 `rule_id`。

### 4.3 `scene_check` — 挡住「宣布完成」，不挡住单次写入

```text
scene_check(scope: "changed" | "all" | [paths])
  → {scene_status, regressions[], signature_set, coverage}
```

P1 静态规则：未迁移类型名、`ext_resource` 死路径、悬空的 ExtResource id。不跑 Godot。签名不含行号。baseline 在 intake 结束时冻结，之后只报相对 baseline 的新增。

实现前先用夹具确认 import 和 `--check-only` 对这几类损坏是否出声。只有两边都沉默的规则，才写成「verify 覆盖不到」。`connection.method` 是否存在先记为待探针，不进第一批规则。

收尾时编排方必须跑 `scope="all"`。模型最多能查 `scope="changed"`。

### 4.4 `trap_scan` — 只报告

只处理 `detection_method=static_scan_post_l0`。成品库里现在是两条：`RectangleShape2D` 的尺寸数值（必须对照转换前快照，不能见到类型名就报警），以及 `project.godot` 里约定键的前后差异。命中写 `needs_human_review`，不调用 `edit`。

shader 报错、autoload 假阳性不归这个函数。它们分别走检索升级和 verify 出口过滤。

---

## 5. `fix_guard` 埋在 `edit` 里

比较过程是确定的；「这是不是一次正确迁移」不是。细则、误伤和漏放见 `DESIGN_NOTES.md`。

| 判据 | 本轮动作 | 抓住什么 | 抓不住什么 |
| --- | --- | --- | --- |
| 1 爆炸半径 | block | 改动远离本轮根因行 | 半径内把函数体掏空 |
| 2 符号消失（func / signal） | block | 删掉整个函数或信号 | 签名还在、函数体换成 `pass` |
| 4 注释化 | block | 把报错行改成注释 | 只删掉半行、或改写成别的空语句 |
| 3 净删除 | 不做（P2，将来先 warn） | — | — |
| 5 场景全文搜旧名 | 不做 | 误伤高。类型是否迁完由 `scene_check` 看 `type=` | — |

`rule_id` 非空时，判据 1 不按脚本行号卡 `.tscn` / `.tres`。跨文件改动必须事先放进 `declared_scope`，并记下理由。新文本解析失败则拒绝落盘。旧文本解析失败时，判据 2 降为 warn，不假装通过。

---

## 6. 明确不做

| 不做 | 原因 |
| --- | --- |
| 给模型 Bash、`write_file`、独立 glob、网络、裸 git | 绕过 `edit` 就绕过 guard |
| 给模型 `codeindex up/status/down/sync` | 生命周期和索引新鲜度由宿主保证 |
| 在进程内调用 `codeindex.cli.cmd_*` | 那些函数会退出进程并污染 stdout |
| 改 verify 入参、改 `RetrievalQuery`、改 CLI 退出码 | 已实现的契约不动 |
| 把 `session_intake` 做成模型工具 | 模型不能选工作区 |
| 把 guard 或 revert 拆成独立工具 | 可以绕过；revert 留在 `edit_revert` |
| 在 verify 里 instantiate 场景或跑 `_ready` | 已写进 godot_mcp 的非目标 |
| 把 `.tscn` 写进 codeindex 的 edges | 场景走 `grep`、`tscn_parse`、`scene_check` |
| 用指标库替换 `InMemoryStateStore` | verify 的熔断计数和跨会话指标不是同一份状态 |
| 机械执行 `apply_and_warn`，或全文替换方法名 | 会改坏转换器故意跳过的行，以及同名变量 |
| 第七个模型工具（`escalate`、`read_scene_tree`、`apply_patch`） | 升级人工看 `hard_stop`；读场景用 `grep` + `read`；写盘只有 `edit` |
| `scene_check` 挡住每一次 `edit` | 只挡住宣布完成 |
| 本轮做场景旁路表、load sweep、ClassDB / I7 | P2，收益在主路径之后 |

---

## 7. 三套状态（现在不实现）

| 存什么 | 放哪 | 现在 |
| --- | --- | --- |
| 无进展、震荡、轮次预算 | verify 的 `InMemoryStateStore`（进程内唯一槽，没有 session 键） | 已实现。Agent 不复制 |
| 对话恢复到哪一步、最后一次 commit、工作区路径 | LangGraph checkpointer | 等主循环 |
| 成本、token、patch hash、guard 裁决、人工标注 | 单独的 SQL 指标库 | 等主循环 |
| 每次工具调用的耗时和 decision | OpenTelemetry span，由编排方包在调用外 | 等主循环 |

检索侧已经有 `set_observer`。本目录的函数只返回结构化结果，不自建第二套观察器。`session_id` 和轮次由编排方传入，不出现在模型参数里。
