# inline_tools — 迁移 Agent 工具面与工作流缺口清单

本目录是 **Agent 可见 MCP 工具** 和 **宿主工作流环节** 的适配层，不改动已落地的
`codebase_index/index` CLI、`godot_mcp.verify`、`rag.retriever` 内部实现。

当前状态：**代码尚未开始**。本文只锁定「还要补什么、谁调用、复用哪段已有代码」。
实现时在本目录加包，禁止回头改 `codeindex` CLI 一行、禁止给 `verify` 加
`workspace_id` / 成本参数、禁止改 `RetrievalQuery` 字段。

---

## 0. 先对齐本库已经定死的事实

用户稿里的工具面和本库已实现契约有三处会踩坑的不一致。本清单按 **已实现部分** 兼容，不按稿纸重画。

| 用户稿说法 | 本库已落地 | 兼容结论 |
| --- | --- | --- |
| edit 每次自己建隔离工作区 | `verify` 是进程内单槽；工作区只来自 `config.yaml` / `CODEBASE_PROJECT_ROOT`；Agent 不能传 `workspace_id` | **工作区是会话级事实**。建仓只允许宿主 intake 做一次。`edit` 只对当前根做 `git apply` |
| Layer 1/2 给 Bash 调 `rg` / `codeindex`（`design.md`） | `codeindex` CLI 七子命令已齐；`godot_mcp` 只注册了 `verify` | **不给 LLM Bash**。否则 `sed -i` 绕过 `edit`，`fix_guard` 作废。CLI 保留给宿主；LLM 只走 MCP adapter |
| 把 `retrieve_cached` 整份 `RetrievalQuery` 暴露给 Agent | `target_version` 有正则，填 `latest` 会拒；`top_k` / `retrieval_mode` 是消融参数 | MCP 只暴露 `error_text` / `symbols` / `query_text` / `kinds?`。版本与 k 从 config / `load()` 注入 |
| 用户稿的「intake」= clone + convert-3to4 | `verify` 内部已有 `phase=intake`：首轮 wipe `*.uid`、建 import 缓存、拍 `.gd/.gdshader/.tres/.uid` 快照 | **两个 intake 不要合并**。verify 内部 intake 已实现，不准外提成工具。宿主那一层改称 **session_intake** |
| 规则库 A 层直接生成机械改名 | A 层按 `detection_method` 分流；`static_scan_post_l0` **禁止**进 `retrieve_migration_rule`；`agent_action=apply_rename` 才是可机械化改名 | `rule_codemod` 只吃 `apply_rename`（及明确可机械化的 `apply_and_warn`）。陷阱扫描另开 `trap_scan`，不进 LLM |

一句话：**verify 校验的那个目录，必须就是 edit / grep / read / codeindex 读写的那个目录。**

```text
session_intake（宿主，一次）
  设 CODEBASE_PROJECT_ROOT + git baseline + convert-3to4 + codeindex up
        │
        ▼
  同一 project_root ─────────────────────────────────────────┐
        │                                                     │
   MCP（LLM 可见，最多 6 个）                                  │
     verify / grep / read / codeindex /                       │
     retrieve_migration_rule / edit(guard)                    │
        │                                                     │
   宿主环节（LLM 不可见）                                       │
     rule_codemod → 走同一 edit 通道                           │
     trap_scan / scene_check / trace_store                     │
──────────────────────────────────────────────────────────────┘
```

---

## 1. 总表：已有 vs 还要补

| 名称 | 调用方 | 本库现状 | 本目录要做 |
| --- | --- | --- | --- |
| `verify` | Agent | **已实现**（`godot_mcp` 唯一工具） | 不改签名。循环里直接调 |
| `grep` | Agent | 设计成 Bash + `rg`，仓库里连 `.rgignore` 都没有 | **新增 MCP adapter**，底层复用 `rg` |
| `read` | Agent | 无 | **新增** |
| `codeindex` | Agent | CLI 已实现；给 Bash 用 | **新增 MCP adapter**；不改 CLI |
| `retrieve_migration_rule` | Agent | `retrieve_cached` / `load()` 已实现；MCP 包装不存在 | **新增 MCP adapter**，裁剪生产 schema |
| `edit`（含 `revert` + `fix_guard`） | Agent + 宿主 `rule_codemod` | 无写通道、无 git 事务、无 guard | **全部新增**（本目录主工作量） |
| `session_intake` | 宿主 workflow | 无。verify 内部 intake ≠ 本环节 | **新增宿主环节** |
| `rule_codemod` | 宿主 workflow | A 层字段已在 `rules.db`；没有生成器、没有落盘 | **新增宿主环节**，落盘必须走 `edit` |
| `trap_scan` | 宿主 workflow | `detection_method=static_scan_post_l0` 已入库；扫描器未写 | **新增宿主环节**（用户稿未单列，本库已规定必须有） |
| `scene_check` | 宿主 workflow | verify 明确不做场景 instantiate / 不做 `.tscn` 死引用扫描 | **新增宿主环节** |
| `trace_store` | 宿主 workflow | Gate 状态在内存，`remaining_budget` 只有轮次 | **新增宿主环节**（不替换 `InMemoryStateStore`） |
| `codeindex up/status/down/sync` | 宿主 | CLI 已实现 | **不暴露给 LLM**。`up` 由 session_intake 调；`sync` 由 `edit` 成功后自动调 |
| Bash / `write_file` / `glob` / 网络 / 裸 git | Agent | 未暴露（正确） | **继续不给** |

---

## 2. Agent 工具面：已有 1 个，再补 5 个（不能再多）

六个工具挂在现有 `godot-mcp` 同一进程上（或本目录一个组合 server 把 `verify` 原样注册进来），共享同一份 `config.yaml`。
**不给** Bash / `write_file` / 独立 `glob` / 网络。`glob` 并进 `grep`（`pattern` 为空时列文件）。

工作区、Godot 二进制、`target_version` 一律从配置注入，工具参数里不许出现。

### 2.1 `verify` — 已实现，本目录不重写

| 项 | 值 |
| --- | --- |
| 归属 | `codebase_index/godot_mcp` |
| 签名 | `kind: "check_file" \| "check_workspace"`；`check_file` 必填 `target` |
| 工作区 | 只读 `project_root` / `CODEBASE_PROJECT_ROOT` |
| 首轮副作用 | `phase=intake`：wipe 工作区 `*.uid`（不碰 `.godot/`）、条件 V3、拍相关后缀快照 |
| 返回 | `VerifyGateResult`：`root_cause_errors[]`（含 `res_path` / `line` / `symbol`）、`pointers`、`hard_stop`、`decision`、`untrusted_files`、`remaining_budget`（仅轮次） |

循环纪律（已写在 verify 契约里，system prompt 必须复述，不是新工具）：

1. `pointers` 非空时只对 `target_res_path` 下钻，禁止对 `res_path` 下钻。
2. `NO_PROGRESS_WARN` 必须换策略，禁止原样重试。
3. `untrusted_files` 非空时禁止宣称完成。
4. `hard_stop=true` 时宿主结束循环，不要再问模型。

`fix_guard` 判据 1（爆炸半径）依赖本工具已经返回的根因行号。不要再做一套「错误列表」工具。

### 2.2 `grep` — 待实现（只读）

| 项 | 值 |
| --- | --- |
| 为什么必须 | **唯一能看见 `.tscn` / `.tres` / `.gdshader` 的通道**。`codeindex` 的 `registry.py` 只认 `.gd/.cs/.cpp/.h/.hpp`，writer 对 `.tscn` 直接 `skipped` |
| 签名 | `(pattern: str \| None, glob?: str, context?: int, max_results?: int) → [{path, line, text}]` |
| `pattern is None` | 退化为按 `glob` 列文件，不再单开 `glob` 工具 |
| 底层 | 直接调已有 `rg`（`--json`），遵守项目 `.gitignore`；排除 `.godot/` `.import/` `.codeindex/` |
| 不做 | 不写盘、不跟索引、不解析场景树 |

Godot 3→4 的类型改名一半在场景里。没有这个工具，LLM 只能改 `.gd`，判据 5（`.tscn` 一致性）也没有输入。

### 2.3 `read` — 待实现（只读）

| 项 | 值 |
| --- | --- |
| 为什么必须 | `git apply` 要精确行号和原文。没有带行号的切片，`edit` 的 hunk 会对不上 |
| 签名 | `(path, line_from, line_to) → 带行号文本` |
| 路径 | 相对 `project_root` 的 `res://` 或 posix 相对路径；禁止绝对路径逃出工作区 |
| 不做 | 不按符号跳转（那是 `codeindex`）；不读 `.godot/` 缓存 |

### 2.4 `codeindex` — 待实现（MCP adapter，不改 CLI）

把已有三条**查询**子命令收成一个工具 + `kind`，风格对齐 `verify`。

| `kind` | 复用 | LLM 参数 |
| --- | --- | --- |
| `find_symbol` | `codeindex find-symbol <name>` / `queries.find_symbol` | `name` |
| `call_chain` | `codeindex call-chain <name> --depth N` | `name`, `depth?`（默认 3） |
| `class_hierarchy` | `codeindex class-hierarchy <name>` | `name` |

**禁止暴露：** `up` / `status` / `down` / `sync`。

- 生命周期是宿主的事（session_intake 调 `codeindex up`）。
- `sync` 由 `edit` 成功后自动调用，绕过 500ms 防抖。这是现有 `cmd_sync` 的设计意图，不要让 LLM 自己记。

适配方式二选一即可：subprocess 调 CLI，或本进程 `connect_ro` + `queries.*`。**不要复制一份 SQL。**

空结果按 CLI 语义返回「查无」，不要包装成「符号不存在、快去改代码」——daemon 没起来应报未就绪，提示宿主先 `up`。

### 2.5 `retrieve_migration_rule` — 待实现（MCP adapter）

| 项 | 值 |
| --- | --- |
| 底层 | 进程启动 `rag.retriever.load()` 一次，之后只调 `retrieve_cached` |
| Agent 可见入参 | `error_text?` / `symbols?` / `query_text?` / `kinds?`（至少一项） |
| 注入、不暴露 | `target_version`（config，禁止 `latest`）、`top_k` / `retrieval_mode`（YAML） |
| 出参 | 原样 `RetrievalResult`：`coverage` / `structured_hits` / `prose_hits` / `recommended_action` / `escalate_suggested` |

路由提示（给宿主，不是工具参数）：

- `coverage=rule_hit` 且 `recommended_action=apply_rename` → 回 `rule_codemod`，不要花钱让 LLM 手写 rename。
- `prose_only` / `no_hit` → LLM 通道（grep / read / codeindex → edit）。
- A 层 `detection_method` 不是 `agent_retrieval*` 的行，检索器本来就看不见。不要在 adapter 里再查 `static_scan_post_l0`。

`rag/README.md` 里的 `@tool RetrievalQuery` 示例**不要直接当生产 schema**——那会把 `target_version` / `top_k` 漏给模型。

### 2.6 `edit` — 待实现（唯一写通道，主工作量）

| `kind` | 入参 | 行为 |
| --- | --- | --- |
| `apply` | `unified_diff` | guard → `git apply` → 单文件粒度 commit → `codeindex sync` 改动文件 |
| `revert` | `to_commit?` | 回到指定 commit 或上一笔 edit commit；不单开 rollback 工具 |

返回：

```text
{ok, commit, guard: {verdict, violations[]}, applied_files[], reject_reason}
```

硬约束（与 verify 同一思路：Gate 埋在工具里，不可绕过）：

1. **不建工作区。** 假定 `project_root` 已是 session_intake 设好的隔离仓，且已有 baseline commit。
2. **guard 在落盘前跑。** 拒绝则不写盘、不 commit、**不消耗 verify 轮次**，只回 `violations`，供 LLM 自纠。
3. **不给 LLM 任何 git 命令。** commit 历史是审计链，不是模型的玩具。
4. 成功后必须 `codeindex sync <applied_files>`，保证下一轮 `find_symbol` 不是陈旧数据。
5. `rule_codemod` 也走这一条通道，保证场景改名和脚本改名受同一套 guard。

---

## 3. `fix_guard` — 埋在 `edit` 里，不单开工具

这是把 verify 从「校验器」升级成「防假修复」的组件。判据复用已有信号，不要另造错误源。

| # | 判据 | 复用 | 优先级 | 失败时 |
| --- | --- | --- | --- | --- |
| 1 | 爆炸半径：hunk 行号必须落在本轮 `root_cause_errors[].line ± N`（建议 N=15） | verify 已返回 `line` + `res_path` | P0 | 拒，不落盘 |
| 2 | 符号消失：apply 后 `codeindex sync`，该文件 `func` / `signal` / `class_name` 数量不得减少（除非 diff 显式声明） | 现有符号表 + `sync` | P0 | 拒，回滚工作区未提交改动 |
| 3 | 净删除行 > 阈值且无对应新增 | 纯 diff 统计 | P1 | 拒 |
| 4 | 新增 `pass` / 整行注释化 / 空函数体 / `# TODO` | 正则 | P1 | 拒 |
| 5 | 改了 `.gd` 的 `class_name` / `func` 名，但同名 token 仍在 `.tscn` | `grep` + 静态 `.tscn` 解析 | P2 | 默认 **标记** `inconsistent_rename`（计入一致性违规指标）；是否硬拒实现时再定 |

判据 1 是本项目独有的：verify 已经滤掉症状、只留带行号的根因。通用 coding agent 没有这个信号。

`rule_codemod` 走 `edit` 时，判据 1 按「机械改名、无单条根因」放行或改用「改动文件集合 ⊆ 符号扫描命中集合」。不要用根因行号把确定性改名误杀。

---

## 4. 宿主工作流层（LLM 看不见）

这些**不是** MCP 工具。写成独立工具会破坏「Agent 不能选工作区 / 不能拼 argv」的一致性。

### 4.1 `session_intake` — 待实现（会话开始，恰好一次）

和 `verify` 内部 `phase=intake` 分工：

| | `session_intake`（本目录要写） | `verify` 内部 intake（已实现，勿动） |
| --- | --- | --- |
| 时机 | MCP 启动之前 | 本进程第一次 `check_workspace` |
| 做什么 | clone + pin → 隔离目录 → `git init` + baseline commit → 设 `CODEBASE_PROJECT_ROOT` → `--convert-3to4` → 大文件 precheck → `codeindex up` → `intake_report.json` | wipe `*.uid`、COLD 时 V3、拍源码快照 |
| 谁调 | 宿主 workflow | `verify` 自己 |

precheck：扫 `>4MB` 或 `>100k` 行的 `.tscn/.tres`。官方 `--convert-3to4` 对这些会**静默跳过**，必须写进报告，否则后面会把「没转」误判成 Agent 没修好。

产出至少包含：converter 改了哪些文件、哪些被跳过、baseline commit、工作区路径。

### 4.2 `rule_codemod` — 待实现（L0 之后、LLM 之前）

从 `rules.db` A 层抽出可机械化行，同时改 `.gd` 和 `.tscn/.tres`，经 **同一 `edit` 通道** 落盘。

合法燃料（本库已有字段，不要重新发明）：

```text
detection_method ∈ {agent_retrieval, agent_retrieval_or_escalate}
  AND agent_action = apply_rename
  AND old_symbol / new_symbol 均非空
```

`apply_and_warn` 可以进「带 warning 的机械改名」，但必须把 `warning` 写进 `intake_report` / trace，不能当静默成功。

不要吃：

- `static_scan_post_l0`（无报错信号的陷阱，见 §4.3）
- `do_not_fix` / `escalate_human` / `note_only`
- 只有散文、没有符号对的 B 层段落

这是「成本每文件」能打赢 baseline 的真实机制：确定性改名 0 token，残差才进 LLM。

### 4.3 `trap_scan` — 待实现（用户稿未单列，本库已规定）

`rag/build/README.md` 已写死：`RectangleShape2D.extents→size` 这类改完**不再报错**、但语义已坏的条目，`detection_method=static_scan_post_l0`，**不进** `retrieve_migration_rule`。

本环节在 L0 / `rule_codemod` 之后跑，命中只写 `needs_human_review`，不调用 `edit`，不花 LLM。
和 `rule_codemod` 是两条管线，不要合成一个「扫库就改」脚本。

### 4.4 `scene_check` — 待实现（收尾，不是循环内工具）

verify 的非目标写得很清楚：不做 DAP、不 instantiate、不跑 `_ready()`。`.tscn` 静默损坏和死引用必须另开通道。

| 档 | 做什么 | 复用 |
| --- | --- | --- |
| 静态（必做） | 解析 `ext_resource` 的 path/type、`node type`、`script = ExtResource(...)`；查死路径、未迁移类型名 | 自写解析；可 internally 调 `grep` |
| smoke（可选） | headless `--script` 里 `ResourceLoader.load()` 遍历 `.tscn`，**只 load 不 instantiate** | 新脚本；不要塞进 `VERIFY_COMMANDS` |

触发点：`hard_stop` 或 `root_cause_errors` 已空，进入收尾报告。不要每轮都跑 smoke。

### 4.5 `trace_store` — 待实现（指标唯一数据源）

两个硬约束逼着必须外置，且**不能**改 verify 内存 Gate：

1. `InMemoryStateStore` 在 MCP 进程内；进程退出即丢熔断计数和快照。跨会话指标必须另存。
2. `remaining_budget` 只有 `rounds_used` / `rounds_limit`。`$/仓库`、token、延迟只能从 trace 算。

建议每轮一行 SQLite：

```text
{round_index, signature_set, decision, patch_hash, guard_verdict,
 tokens, cost_usd, latency_ms, commit}
```

写入方是宿主：每次 `verify` / `edit` / `retrieve` 返回后记账。不要让 LLM 调这个库。

不要用 trace 替换 Gate 的进程内状态——震荡 / 无进展算法继续只认内存 store。

---

## 5. 一轮循环（宿主编排，节点不是工具）

```text
session_intake（一次）
  ├ 隔离仓 + git baseline + 设 CODEBASE_PROJECT_ROOT
  ├ --convert-3to4 + precheck（>4MB 静默跳过）
  └ codeindex up
        ↓
rule_codemod ──(A 层 apply_rename, .gd + .tscn)──→ edit(guard)
        ↓
trap_scan ──(static_scan_post_l0，只报告不改)──→ 写入报告
        ↓
   ┌─────────── verify(check_workspace) ───────────┐
   │  hard_stop? ──yes──→ scene_check + 报告         │
   │  root_cause_errors 为空? ──yes──→ 同上         │
   │  否 ↓                                          │
   │  retrieve_migration_rule(root_cause[0])        │
   │    ├ A 层命中 + apply_rename → 回 rule_codemod  │
   │    └ prose_only / no_hit → LLM 通道            │
   │         grep / read / codeindex → edit(guard)  │
   │         guard 拒 → 返回 violations，不计 verify 轮 │
   └────────────────────────────────────────────────┘
        ↓
   每步 → trace_store.append(...)
```

LLM 在菱形框里只看得到六个 MCP 工具。方框外的节点由宿主代码推进。

---

## 6. 明确不做

| 不做 | 原因 |
| --- | --- |
| 给 LLM Bash / `write_file` / 独立 glob / 网络 | 绕过 `edit` 即绕过 guard |
| 给 LLM `codeindex up/status/down/sync` | 生命周期与索引新鲜度是宿主不变量 |
| 给 LLM 裸 git / 选 `workspace_id` | 与 verify 单槽工作区冲突 |
| 改 `codeindex` CLI、改 `verify` 入参、改 `RetrievalQuery` | 「已实现不动」 |
| 把 `session_intake` 做成 MCP 工具 | Agent 不能选工作区 |
| 把 `fix_guard` / `revert` 拆成独立工具 | 可绕过；revert 已合并进 `edit` |
| 在 verify 里跑 scene instantiate / `_ready` | 已写进 `godot_mcp` 非目标 |
| 把 `.tscn` 塞进 codeindex | 场景走 `grep` + `rule_codemod` + `scene_check` |
| 用 trace 替换 `InMemoryStateStore` | Gate 算法与跨会话指标生命周期不同 |
| 第七个 Agent 工具（含 `escalate` / `read_scene_tree` / `apply_patch`） | 升级人工是宿主看 `hard_stop`；场景阅读用 `grep`+`read`；写盘只有 `edit` |

---

## 7. 建议实现顺序

按依赖，不按用户稿章节号：

1. **`grep` + `read`** — 无状态，edit 的前置。
2. **`codeindex` adapter** — 只包查询；确认 `up` 仍由宿主调。
3. **`retrieve_migration_rule` adapter** — `load()` 一次；config 增补 `target_version`（现有 `config.example.yaml` 还没有这个字段）。
4. **`edit` + `fix_guard` P0**（爆炸半径 + 符号消失）— 写通道闭环。
5. **`session_intake` 最小集** — 隔离仓 + `git init` + 设环境变量 + `codeindex up`。没有它，本地只能手填 `config.yaml`，但工具契约已经成立。
6. **`rule_codemod`** — 有 `edit` 之后才能保证 `.gd`+`.tscn` 原子落盘。
7. **`trace_store`** — 开始跑循环就要记，否则成本指标永远算不出来。
8. **`fix_guard` P1/P2、`trap_scan`、`scene_check`** — 防假修复与收尾通道，不挡主路径打通。

---

## 8. 本目录与已有包的关系

```text
inline_tools/          ← 本目录：adapter + 宿主环节（待实现）
  README.md            ← 本文件（缺口清单，进 git）
  docs/                ← 就地设计笔记（gitignore）

codebase_index/index   ← 已实现 CLI / daemon；本目录只调，不改
codebase_index/godot_mcp
  verify               ← 已实现 MCP；本目录不重写
rag/retriever          ← 已实现 retrieve_cached；本目录只包一层
```

共享配置继续是 `codebase_index/config.yaml`。新增字段只允许：

- `target_version`（给 retrieve adapter 注入，例如 `4.7.1`）
- 可选：`guard.radius_lines`、`guard.max_net_deleted`

不要在工具参数里再收一遍这些值。
