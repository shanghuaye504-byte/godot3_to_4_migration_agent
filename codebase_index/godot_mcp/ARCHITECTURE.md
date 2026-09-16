# godot_mcp — 架构说明（Layer 3 内部视角）

> 定位：本文件讲**这一个目录内部**怎么组织、进程之间怎么配合、出错时怎么处理。
> 三层总体取舍（为什么 Layer 1 不建工具、Layer 2 为什么拆 daemon/CLI 两进程）见
> `../design.md`；本目录对外的"怎么跑起来"见 `README.md`；一步步实现的顺序见
> `docs/implementation_order.md`。三份文档职责不重叠，改动时不要互相抄。
>
> **范围降级说明**：原规划包含常驻 LSP 会话（`hover_symbol` / `workspace_symbol`）+
> `verify` 共三个工具。由于 LSP 会引入不可预测的进程/端口冲突，且时间紧张，现决定
> **完全去掉 LSP 方案**。本目录只保留 `verify` 工具；引擎语义查询统一由 Layer 2 的
> `codeindex` CLI 承担。

## 1. 这一层要解决什么问题

Agent 改完代码后，需要一条"客观信号"来判断改动是否真的让 Godot 4.x 满意。
Layer 2（`../index/`）的 tree-sitter 索引只能回答"项目里有哪些符号、谁调用谁"，
无法回答"这条改动能不能过 Godot 解析器"。

`godot_mcp` 就是把这个"真实拉起 Godot 二进制做校验"的动作，包成一个 MCP 工具
`verify` 暴露给 Agent。它不做 Layer 2 已经覆盖的符号查询能力。

## 2. 进程模型：一次性校验子进程

```text
                    ┌───────────────────────────────────────┐
                    │           godot_mcp（本进程，Python）  │
  Agent ── stdio ──▶│  server.py：注册 verify 工具          │
   MCP 客户端        │                                       │
                    │   ┌──────────────────┐                │
                    │   │ verify/runner    │                │
                    │   │ 一次性子进程      │                │
                    │   │ spawn→collect→exit│               │
                    │   └────────┬─────────┘                │
                    │            │ argv（固定白名单）        │
                    │   ┌────────▼────────┐                 │
                    │   │ godot4          │                 │
                    │   │ --headless      │                 │
                    │   │ --check-only    │                 │
                    │   │（跑完即退出）    │                 │
                    │   └─────────────────┘                 │
                    │            │                          │
                    │   ┌────────▼────────┐                 │
                    │   │ verify_shell    │                 │
                    │   │ verify_filter   │                 │
                    │   │ verify_gate     │                 │
                    │   └─────────────────┘                 │
                    └───────────────────────────────────────┘
```

`verify/runner.py` 管理一次性 Godot 子进程：

| | `verify/runner.py` |
| --- | --- |
| 生命周期 | 每次 `verify` 工具调用现起一个，跑完就收 |
| 失败处理 | 一次性判定：超时 / 退出码非零，不重试 |
| 状态 | 无状态（每次都是全新进程） |
| 通信方式 | 标准 argv + stdout/stderr（`subprocess`） |

## 3. `verify` 工具的调用路径

```text
verify(kind=check_file|check_workspace, target?)
  └─▶ workspace_lock + 拒收 C#/GDExtension
        └─▶ 内部组装 phase / unified_diff / previous_view
        └─▶ check_file：COLD 时先 V3，再一次 V2（不写快照、不查体积）
              └─▶ filter → merge → annotate_check_file_view（A/B）→ Gate
        └─▶ check_workspace：scan_workspace（相关后缀 ≤2000 文件 / 1 GiB，超限硬拒）
              └─▶ verify_shell.collect_workspace_view（不调用 annotate）
                    ├─▶ 条件 V3（COLD / 触发表 / 入队 wipe）
                    ├─▶ V1 → V2 下钻 → 再 V1 直到 pointer 稳定（V1 ≤3 轮，V2 ≤50 个 target）
                    └─▶ 收尾门 V3（GDScript 完成后）
                          └─▶ verify_gate.algorithm.evaluate(...)
                                └─▶ VerifyGateResult
```

`verify` 返回值包含过滤后的错误视图 **以及** Gate 判定（继续 / 无进展 /
单文件卡住 / 震荡 / 轮次耗尽 / 基础设施熔断）。`hard_stop=True` 时，
宿主 Agent 循环应在工具调用返回后强制结束会话。

字段级契约（MCP schema、JSON 返回值、参数如何接到 `run_verify_tool`）见
[`docs/mcp_verify_tool_interface.md`](docs/mcp_verify_tool_interface.md)。

## 4. 失败模式与处理原则

| 失败场景 | 处理方式 | 对应代码 |
| --- | --- | --- |
| `--check-only --debug` 掉进交互式 debugger 挂死 | `runner.py` 必须有 subprocess timeout，超时后 `killpg` 整个进程组 | `verify/runner.py` |
| 校验子进程正常退出但带报错 | 不算"执行失败"，`VerifyResult.timed_out=False`，报错内容交给 `verify_filter` 判断是不是真 error | `verify/runner.py` + `verify_filter/` |
| `[autoload]` 白名单 KEY 的 `Identifier not found`（N01/N02，R2） | 过滤器 drop，记 `compile_truncated` + `untrusted_files`，不进根因 | `verify_filter/rules/autoload_fp.py` |
| `class_name` 缓存陈旧（N03）或非白名单 `Identifier not found`（N02 漏网） | 过滤器不动。仅 `check_file` 外壳：A 把 Identifier 挪出根因并打 `class_cache_stale`；B 保留根因并打 `identifier_not_found_maybe_unregistered_autoload:{symbol}` | `verify_shell/class_cache.py` + `verify_shell/check_file_annotate.py` |
| warning 被误当修复目标 | `ClassifiedEvent.kind` 严格区分 error/warning，Gate 只看 error | `verify_filter/models.py` |
| Agent 试图拼自由 verify 命令行 | MCP `kind` 仍是二选一（`check_file`→V2，`check_workspace`→V1）；内部白名单只有探针子集 V1/V2/V3，不含 `--debug` | `server.py` 的输入 schema + `verify/commands.py` |
| 相关后缀全文快照超过 2000 个文件或 1 GiB | 本轮开始硬拒，`SnapshotTooLargeError`，不截断、不 `save` 半截快照 | `verify_shell/snapshot.py` |

## 5. 明确的非目标（Non-goals）

- **不做 LSP 语义查询**：`hover` / `workspace/symbol` 已移除。引擎内置符号/语法
  容错查询统一走 Layer 2 的 `codeindex` CLI。
- **不做运行时检验**：不涉及 DAP、不实例化场景树、不执行 `_ready()` / `_process()`。
  `--check-only` 是静态分析。
- **不做通用命令执行器**：Agent 只能选 MCP 二选一；内部只能跑探针锁定的 V1/V2/V3，
  不接受任意 flag 拼接。
- **不重复 Layer 2 的能力**：符号定义 / 调用链 / 类层次结构一律走 `index/` 的
  `codeindex` CLI，本层只补"真实 Godot 校验"这一块。
- **不改用户原仓的 git 历史**：入队 UID wipe 只 `unlink` 隔离工作区里的 `.uid`，
  不做 `git rm`。`.godot/` 只在 V3 触发器命中时由 Godot 自己重建，禁止无故 `rm -rf`。

## 6. 与 index/（Layer 2）的关系

两者是**平级、互不 import 的独立 Python 包**，运行时是完全独立的进程，唯一的
耦合点是共享同一份 `../config.yaml`（各自的 `config.py` 只读自己用得到的字段，
见各自 `config.py` 文件头的字段表）。任何一边的内部重构都不应该要求改动另一边。
