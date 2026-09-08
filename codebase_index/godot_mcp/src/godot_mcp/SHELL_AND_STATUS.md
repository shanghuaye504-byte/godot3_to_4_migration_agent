# 外壳逻辑、V1/V2/V3 运作与 MCP 完成度

本文写在 `src/godot_mcp/` 根目录，给开发者对照代码读。权威规格仍是
`docs/verifier_filter_scheme.md` §2.1 / §12 与 `docs/verifier_retry_gate_scheme.md`。
就地实现笔记见 `docs/shell_walkthrough.md`。

---

## 1. 这一层怎么封装

Verifier 不是「一条 Godot 命令」。它拆成四层，MCP 只是最外面的薄壳：

| 层 | 目录 | 职责 | 有没有副作用 |
| --- | --- | --- | --- |
| 命令与进程 | `verify/` | 白名单 argv（V1/V2/V3）、起子进程、超时 `killpg`、V1 写/删哨兵 | 有：Godot 进程、写 `__probe_sentinel.gd` |
| 噪声过滤 | `verify_filter/` | 把一份 stdout/stderr 变成 `FilterResult`，再 `merge` 成项目视图 | 无：纯函数 |
| 外壳编排 | `verify_shell/` | **何时、按什么顺序**跑 V1/V2/V3；锁、拒收、UID wipe、触发表 | 有：锁、删 `.uid`；Godot 只通过注入的 `spawn` |
| 重试门 | `verify_gate/` | 跨轮：无进展 / 震荡 / 熔断 / 预算 | 有：读写会话状态（当前是内存） |
| MCP | `server.py` | 注册 `verify`，把参数转给 `run_verify_tool` | 无业务：stdio 传输 |

胶水在 `verify_gate/tool.py` 的 `run_verify_tool`：

```text
MCP verify(kind, target?)
  └─ workspace_lock(project_root)
       ├─ 拒收 *.csproj / *.gdextension
       ├─ 从 StateStore 推导 phase（首轮 intake）、snapshot diff、previous_view
       ├─ kind=check_file  → COLD 时先 V3，再一次 V2 → filter → merge
       └─ kind=check_workspace
            ├─ phase=intake 时 wipe 工作区 *.uid
            └─ collect_workspace_view(...)     ← 外壳本体
                 └─ evaluate(Gate) → VerifyGateResult
```

Agent **不能**自己拼 Godot flag，也 **不能**直接点 V3。MCP 只暴露：

- `check_file` → COLD 时先 V3 再 V2（单文件）
- `check_workspace` → 内部走完整外壳（V3 由外壳决定）

`VERIFY_COMMANDS` 的 key 是 `V1` / `V2` / `V3`。V4–V8 不进白名单（V8 `--debug` 会 signal 11）。

---

## 2. V1 和 V2 怎么运作

### 2.1 V1：项目级扫描（带哨兵）

argv（探针锁定）：

```text
godot --headless --path $P --check-only --script res://__probe_sentinel.gd --quit
```

裸 `--check-only` 不带 `--script` 是 no-op，所以必须有哨兵。

`verify/runner.py` 在 `kind == "V1"` 时：

1. `sentinel.install_sentinel`：扫描项目内 `*.gd`（排除 `__probe_` 前缀和 `.godot/`），按相对路径排序，写成

   ```gdscript
   extends RefCounted
   const _p0 = preload("res://a.gd")
   const _p1 = preload("res://b.gd")
   ```

2. 起 Godot
3. `finally` 删除 `__probe_sentinel.gd`（超时/崩溃也删）

V1 **报不全、也不报具体语法**（N04 / N08）：它往往只打出

```text
Parse Error: Could not preload/resolve script "res://root_bad.gd"
at: res://__probe_sentinel.gd   ← 引用方
```

filter 把这类行标成 `role=pointer`，`target_res_path=res://root_bad.gd`。
哨兵自己的 `Failed to compile depended scripts` / `Failed to load script` 会被 R1 丢掉，**不会**拿去跑 V2。

### 2.2 V2：单文件，用来消化 pointer

argv：

```text
godot --headless --path $P --script res://X.gd --check-only --quit
```

`X.gd` 必须是 pointer 的 **target**（坏文件），不是哨兵，也不是引用方。
对 `res://root_bad.gd` 跑 V2 才能看到真正的 `Unexpected Indent` 一类根因。

### 2.3 一次 check_workspace 里 V1↔V2 怎么转

实现：`verify_shell/collect.py`。

```text
v2_by_target = {}          # 累积，已经 V2 过的 target 不再跑
最多 8 轮 V1：
    跑 V1 → filter
    对每个 pointer.target_res_path：
        若还没 V2 过，且总数 < 8：
            跑 V2 → filter，写入 v2_by_target
    若本轮没有新增任何 V2 → 停止（pointer 集已稳定或本来就没有 pointer）
    否则再 V1（N04：哨兵提前结束，autoload / 更深 preload 可能上一份日志里没有）
merge_command_results(最新 V1, 全部 V2, 可选 V3)
```

**有没有对 V1 探出的 pointer 分别跑 V2？有。**  
每个尚未见过的 `target_res_path` 各跑一次 V2，结果按 target 累积。同一 target 不重复。单次 V2 超时/崩溃：**跳过该 target**（pointer 留在 `pending_pointers`），不把整轮打成 INFRA。V1 或 V3 超时/崩溃：整轮 `INFRA_FAILURE`。

上限：V1 最多 8 轮，V2 最多 8 个不同 target。超出的 pointer 会留在 `pending_pointers`，项目级不算完成。

---

## 3. 有没有提前 V3 预热？中途何时跑 V3？

有预热，但是**条件性的**，不是「每次 V1 前无脑 import」。判定全在 `verify_shell/trigger.py` 的 `should_run_v3`，三个 phase 禁止混用。

WARM 的唯一判据：存在 `.godot/global_script_class_cache.cfg`。空 `.godot/` 目录仍是 COLD。

### 3.1 采集开始前（预热 / 入队）

`collect_workspace_view` 在第一轮 V1 **之前**先问一次 `should_run_v3(..., phase=intake|iteration)`：

| 条件 | 跑不跑 V3 | 原因 |
| --- | --- | --- |
| `phase=intake` 且缓存是 COLD | 跑 | 入队必须先建 class cache |
| `phase=intake` 且刚 wipe 了 `.uid` | 跑 | N06：删 sidecar 后必须 import 重建 |
| `phase=iteration` 且缓存是 COLD | 跑 | **这就是预热**：禁止在 COLD 上采集 V1/V2，否则 `class_name` 假阳性会被当成真缺失（N03） |
| `phase=iteration` 且 WARM，diff 命中触发表 | 跑 | 见下一节 |
| `phase=iteration` 且 WARM，普通 `.gd` 函数体 / 空 diff | **不跑** | 默认路径，省 import 成本 |

MCP 默认不再让 Agent 填 `phase`。`tool.py` 在 `rounds_used == 0` 时推 `intake`，之后 `iteration`。入队几乎总会先 V3（COLD 或刚 wipe `.uid`）。

### 3.2 中途（本轮 patch 触发表）

只看 **unified diff 文本**，不起 Godot 来问「要不要 import」。`phase=iteration` 且已经 WARM 时，下列任一为真就在 V1 循环**之前**再跑一次 V3：

- diff 行匹配 `^[+-]class_name\s`（新增/删除/改名 `class_name`）
- diff 新增了 `.gd` 文件
- 改动路径以 `.gdshader` / `.shader` 结尾
- `.tres` hunk 里出现 `.gdshader` 或 `shader_type`
- 本轮在修 UID 重复：diff 删除了 `.uid`，或上一份视图里有 `UID duplicate` 根因且本轮动了那些路径

不触发：普通函数体、只改 autoload 引用、`.tscn` 改 `ext_resource`、单条 `.uid` 文本被改（非重复簇修复）。

### 3.3 收尾门（V1/V2 之后）

V1↔V2 收敛并 `merge` 之后，若：

- `project_view.gdscript_complete`（根因为空 **且** 没有未消化 pointer）
- **且** 本轮还没跑过 V3

则再跑一次 V3，专门补 shader / UID 重复（N07：这些 V1/V2 看不见）。收尾打出新根因 → 本轮 `HAS_ERRORS`，回 Agent。  
若本轮开头已经为了预热/触发表跑过 V3，收尾门**不再跑**（`v3_ran=True`）。

`merge` 时 `v3 is None` 会带 caveat `shader_not_checked`，不能对外宣称迁移完成。

### 3.4 `check_file` 的 COLD 预热

单文件通道在缓存 COLD 时先跑一次 V3 再建 class cache，然后才 V2。已 WARM 则仍只跑一次 V2，不跑收尾门。项目级完成必须以 `check_workspace` 为准。

---

## 4. 一次 check_workspace 的时序图

```text
lock + 拒收
    │
    ├─ phase=intake? → 删除工作区 *.uid
    │
    ▼
should_run_v3(intake 或 iteration) ?
    是 → V3（预热 / 触发表）  失败则整轮 INFRA，不再 V1
    │
    ▼
loop（≤8）:
    V1 + 哨兵
    filter → pointers
    对每个新 target 各跑 V2（≤8 个）
    没有新 V2 → break
    有新 V2 → 再 V1
    │
    ▼
merge(V1, 全部 V2, 若有则 V3)
    │
    ▼
gdscript 已完成 且 本轮还没 V3 ?
    是 → 收尾门 V3 → 再 merge
    │
    ▼
Gate.evaluate（跨轮判定）
```

---

## 5. MCP 工具完成度

对外仍只有一个工具 `verify`。对「Godot 3→4 迁移 Agent 的客观 reward」这一层，**本包业务闭环已经能跑通**：起进程 → 滤噪声 → 按探针规则编排 V1/V2/V3 → 跨轮熔断/无进展。

字段级契约（MCP schema、JSON 返回值、Agent 参数如何接到 `run_verify_tool`）见
[`docs/mcp_verify_tool_interface.md`](../../docs/mcp_verify_tool_interface.md)。

### 5.1 已完成

- 指令白名单 V1/V2/V3，禁 `--debug` / `--verbose`
- runner：超时、进程组 kill、超时≠失败
- V1 哨兵写入/删除
- `verify_filter` 全套规则 + merge（黄金样例）
- 外壳：锁、拒收 C#/GDExtension、入队 UID wipe、COLD 预热、触发表、V1↔V2 收敛、收尾门
- Gate：熔断 / 预算 / 震荡 / 无进展 / 单文件卡住（内存状态）
- MCP：`verify(kind, target?, session_id, workspace_id?, round_cost_usd)`；`phase` / `unified_diff` / `patched_files` 由内部快照组装
- 返回值含 `gdscript_complete` / `shader_checked` / `probe_incomplete`；未消化 pointer 带 `pointer_budget_exhausted` 或 `pointer_probe_incomplete` caveat

### 5.2 本包内还没做（明确缺口）

| 缺口 | 影响 | 说明 |
| --- | --- | --- |
| Redis `StateStore` | 多 worker 不能共享熔断/签名历史 | 接口留了，只有 `InMemoryStateStore` |
| 调用方必须自己提供隔离工作区 | `wipe_uid` 作用在 `config.project_root` | 若指向用户原仓，会删人家的 `.uid`（不做 git rm，但文件没了） |
| 工作区锁是本机 flock | 跨机器/跨容器无效 | 分布式要换 Redis 锁（方案里的 N14 进阶） |
| V5 交叉验证 | 无 | 探针确认不能当 reward，故意不进白名单 |
| V2 上限 8 / V1 上限 8 | 大项目 pointer 可能消化不完 | `probe_incomplete=True` 且 caveat `pointer_budget_exhausted`；须再调 `check_workspace` |

### 5.3 不在本 MCP 包范围（整个迁移 Agent 还没做）

这些不是外壳漏写，是上一层产品：

- L0 `--convert-3to4` / 确定性 rename 表
- Agent ReAct 循环、读文件 / 打补丁工具
- RAG `retrieve_migration_rule`
- Agent-as-Judge（语义保真，防「删行骗过编译器」）
- FastAPI 网关、Redis Streams 任务队列、多 worker
- 入队预扫描大文件、把仓库 copy 到隔离 workspace 的服务

---

## 6. 测试方案（按模块、由浅到深）

工作目录一律：

```bash
cd codebase_index/godot_mcp
```

全部测试都**不依赖本机 `godot4`**（runner / collect 用假二进制或 mock `spawn`）。`-v` 可以看到每条用例名字，建议第一次按文件拆开跑。

### 6.1 叶子：外壳判定（不起 Godot）

```bash
# 缓存：空 .godot/ 仍是 COLD；有 global_script_class_cache.cfg 才 WARM
uv run pytest tests/verify_shell/test_cache.py -q -v

# 拒收：项目根有 Game.csproj 要抛；.godot 里的同后缀不管
uv run pytest tests/verify_shell/test_reject.py -q -v

# UID：只删 main.tscn.uid，保留 .godot/imported/*.uid
uv run pytest tests/verify_shell/test_uid.py -q -v

# diff：新 gd + class_name、.gdshader、.tres 里的 shader、删除 .uid
uv run pytest tests/verify_shell/test_diff.py -q -v

# snapshot：工作区相对上一轮快照拼出的 diff 能喂给触发表
uv run pytest tests/verify_shell/test_snapshot.py -q -v

# 触发表：intake COLD 必 V3；WARM 普通函数体不 V3；改 class_name 要 V3
uv run pytest tests/verify_shell/test_trigger.py -q -v

# 锁：持锁时 nonblocking 第二次失败；释放后能再抢
uv run pytest tests/verify_shell/test_lock.py -q -v
```

看单条：

```bash
uv run pytest tests/verify_shell/test_trigger.py::test_iteration_class_name_triggers -q -v
```

### 6.2 采集循环（mock spawn，看命令顺序）

```bash
uv run pytest tests/verify_shell/test_collect.py -q -v
```

三件关键事实：

1. `test_cold_runs_v3_then_v1_v2_then_repeat_v1`  
   COLD → 顺序必须是 **`V3, V1, V2, V1`**：先预热，V1 打出 pointer 后对 `res://root_bad.gd` 跑 V2，再 V1 一次确认没有新 pointer。
2. `test_warm_clean_v1_then_final_gate_v3`  
   已 WARM 且 V1 干净 → **`V1, V3`**：开头不预热，收尾门补 shader/UID。
3. `test_v3_timeout_is_infra_before_v1`  
   预热 V3 超时 → 整轮 INFRA，**不会**再跑 V1。

### 6.3 胶水 + Gate（仍 mock 子进程）

```bash
uv run pytest tests/test_verify_tool.py -q -v
```

覆盖：真语法错误的返回形状、连续 3 次超时熔断、3 轮相同签名 `NO_PROGRESS_WARN`、workspace 下钻（COLD 时 kinds 为 `V3,V1,V2,V1`）、C# 项目拒收、`check_file` 缺 target。

```bash
uv run pytest tests/test_server.py -q -v
```

只测 MCP 包装：工具列表只有 `verify`、缺配置是 `ToolError`。

### 6.4 更下层（改外壳时也应回归）

```bash
# 指令白名单仍是 {V1,V2,V3}，V1 指向哨兵且带 --quit
uv run pytest tests/test_commands.py -q -v

# 哨兵扫描排序、排除 __probe_ 与 .godot、跑完删除
uv run pytest tests/test_sentinel.py tests/test_runner.py -q -v

# 过滤器黄金样例（不要在外壳任务里改这些）
uv run pytest tests/verify_filter/ -q

# Gate 算法
uv run pytest tests/verify_gate/ -q
```

### 6.5 全量

```bash
uv run pytest tests/ -q
```

### 6.6 REPL 手摸流程（可选）

```bash
uv run python
```

```python
from pathlib import Path
from godot_mcp.verify_shell import cache_is_warm, parse_unified_diff, should_run_v3
from godot_mcp.verify_shell.snapshot import diff_snapshots, scan_workspace

root = Path("/tmp/fake-godot-proj")
root.mkdir(exist_ok=True)
print("warm?", cache_is_warm(root))  # False → iteration 会先 V3 预热

(root / "a.gd").write_text("class_name Foo\n", encoding="utf-8")
old = scan_workspace(root)
(root / "a.gd").write_text("class_name Bar\n", encoding="utf-8")
diff = parse_unified_diff(diff_snapshots(old, scan_workspace(root)))
print(should_run_v3(root, diff, None, phase="iteration", v3_ran=False))
```

采集循环不必起 Godot：抄 `tests/verify_shell/test_collect.py` 里的假 `spawn`，打印每次 `kind` / `target` 即可看到 V1 pointer 是否分别变成了 V2。
