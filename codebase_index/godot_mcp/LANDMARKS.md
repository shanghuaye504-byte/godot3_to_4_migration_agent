# `codebase_index/godot_mcp` 模块路标 (LANDMARKS)

> **上级路标**：[`codebase_index/LANDMARKS.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/LANDMARKS.md)
> **叶子节点**：本目录无下级子目录路标。

## 1. 模块现状与已核实的 Bug 清单

`godot_mcp` 实现了完整的四阶段 Godot Headless 验证栈：
1. `verify/`：进程组管理、超时强杀、stderr 状态机解析、autoload/ext_resource 富化、诊断指纹计算。
2. `verify_filter/`：硬丢弃（`HARD_DROP`）、条件信号抑制（`UID_WARNING`、`AUTOLOAD_FALSE_POSITIVE`、`RES_PATH_MISSING`）、`CASCADE_SYMPTOM` 级联折叠。
3. `verify_gate/`：单工作区状态机（轮次上限、无进展升级、A→B→A 震荡中止、Patch 回滚、基础设施熔断）。
4. `verify_shell/`：V3 一次性全量修复重导触发器、工作区快照与原子回滚。

经源码逐行核查，发现以下 **5 个具体缺陷** 与 **1 项去过度设计清理**：

| 编号 | 文件与行号 | 问题描述 | 严重度 |
| :--- | :--- | :--- | :--- |
| **MCP-BUG-1** | [`src/godot_mcp/verify_gate/tool.py:98-105`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_gate/tool.py#L98-L105) | **`check_file` 污染 `check_workspace` 的状态机历史**：`run_verify_tool(kind="check_file")` 与 `check_workspace` 共用同一个 `WorkspaceVerifyState` 并调用 `evaluate()`。当 Agent 执行 `check_workspace` (`{A, B}`) → `check_file("clean.gd")` (`∅`) → `check_workspace` (`{A, B}`) 时，`signature_history` 变为 `[{A,B}, ∅, {A,B}]`，满足 `history[-1] == history[-3] != history[-2]`，**100% 误触发 `OSCILLATION_ESCALATE` (`hard_stop=True`)**，还会白白消耗 `rounds_used` 并误报 `REGRESSION_DETECTED` | **致命 (P0)** |
| **MCP-BUG-2** | [`src/godot_mcp/verify_gate/algorithm.py:101-136`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_gate/algorithm.py#L101-L136) | **`circuit_state == "OPEN"` 未在 `evaluate()` 入口短路**：当连续 3 次基础设施故障将 `state.circuit_state` 置为 `"OPEN"` 后，若后续再次调用且 `infra_status == "OK"`，第 126 行会将 `infra_failure_streak` 清零并返回 `CONTINUE`，使半永久打开的熔断器失效 | **高 (P0)** |
| **MCP-BUG-3** | [`src/godot_mcp/verify_gate/tool.py:66`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_gate/tool.py#L66) | **`load_retry_gate_config()` 未传入配置文件路径**：第 66 行无参调用 `load_retry_gate_config()`（默认 `path=None`），导致 `config.yaml` 中的 `retry_gate:` 配置段永远被忽略 | **中 (P1)** |
| **MCP-BUG-4** | [`src/godot_mcp/verify_shell/snapshot.py:14`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_shell/snapshot.py#L14) | **工作区快照漏掉 `.tscn` 与 `.godot` 文件**：`SNAPSHOT_SUFFIXES = {".gd", ".gdshader", ".shader", ".tres", ".uid"}` 未包含 `.tscn` 和 `.godot`（如 `project.godot`），导致 V3 自动修复或 Agent 修改场景/项目配置失败回滚时无法恢复 `.tscn` 与 `project.godot` | **高 (P1)** |
| **MCP-BUG-5** | [`src/godot_mcp/verify_shell/trigger.py:18,34`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_shell/trigger.py#L18)、[`class_cache.py:15`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_shell/class_cache.py#L15)、[`uid_cluster.py:70`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_shell/uid_cluster.py#L70) | **V3 触发器两处盲区**：① `class_name` 正则 `r"^class_name\s+(\S+)"` 无法匹配同一行带有 `@tool` 前缀的声明（`@tool class_name Foo`）；② `UID_DUPLICATE` 事件仅在 `event.res_path` 记录了 `min(path_a, path_b)`，若 Agent 修改的是 `max(path_a, path_b)` 来消除重复 UID，`is_uid_duplicate_repair` 无法触发 V3 重刷缓存 | **中 (P1)** |
| **MCP-CLN-1** | [`src/godot_mcp/verify_gate/state_store.py:148-167`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_gate/state_store.py#L148-L167) | **删除过度设计的 `RedisStateStore` 占位类**：架构已明确移除 Redis 服务层，`InMemoryStateStore` 即可满足单工作区进程内闭环需求 | **低 (P2)** |

---

## 2. 逐项修复指导

### 2.1 隔离 `check_file` 与 `check_workspace` 的门控状态 (`MCP-BUG-1`)

在 [`src/godot_mcp/verify_gate/tool.py:94-108`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_gate/tool.py#L94-L108) 中：
- `check_file` 的定位是**局部语法/类型快速探测**（只检查单个 `.gd` 文件，不包含全工作区其他文件的错误签名）。
- 因此，当 `kind == "check_file"` 时：
  1. 如果 `state.circuit_state == "OPEN"` 或 `infra_status != "OK"`，仍然走 `evaluate()` 更新基础设施熔断计数并持久化。
  2. 如果 `infra_status == "OK"`，**不要**将单文件 `sig_set` 追加到 `state.signature_history`，**不要**递增 `state.rounds_used`，也**不要**与全库 `last_good_signatures` 对比触发 `REGRESSION_DETECTED`；而是直接根据单文件 `error_count` 构造 `GateOutput(action="PASS" if error_count == 0 else "CONTINUE", ...)` 返回。

```python
    if kind == "check_file" and filter_result.infra_status == "OK" and state.circuit_state != "OPEN":
        sig_set = frozenset(d.signature for d in filter_result.primary_diagnostics)
        gate_output = GateOutput(
            action="PASS" if len(sig_set) == 0 else "CONTINUE",
            reason="check_file passed." if len(sig_set) == 0 else "check_file has errors.",
            hard_stop=False,
            rollback_patch_id=None,
            target_signatures=sorted(sig_set),
            active_error_count=len(sig_set),
            rounds_used=state.rounds_used,
            no_progress_streak=state.no_progress_streak,
            circuit_state=state.circuit_state,
        )
    else:
        gate_output = evaluate(state, request, retry_cfg)
        store.save(state)
```

---

### 2.2 在 `evaluate()` 入口短路已开启的熔断器 (`MCP-BUG-2`)

在 [`src/godot_mcp/verify_gate/algorithm.py:110-125`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_gate/algorithm.py#L110-L125) 中，在检查 `request.infra_status != "OK"` 之前，先判断 `state.circuit_state == "OPEN"`：

```python
    # Step 1a: 若熔断器已处于 OPEN 状态，直接短路返回 CIRCUIT_OPEN
    if state.circuit_state == "OPEN":
        return _make_output(
            state,
            action="CIRCUIT_OPEN",
            reason="Infrastructure circuit breaker is already OPEN.",
            hard_stop=True,
            rollback_patch_id=None,
            sig_set=sig_set,
        )
```

---

### 2.3 传递配置文件路径给 `load_retry_gate_config` (`MCP-BUG-3`)

1. 在 [`src/godot_mcp/config.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/config.py) 的 `McpConfig` 数据类中增加字段 `config_path: Path | None = None`，并在 `load_config()` 中记录实际加载的 `resolved_path`。
2. 在 [`src/godot_mcp/verify_gate/tool.py:66`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_gate/tool.py#L66) 中改为：

```python
retry_cfg = load_retry_gate_config(cfg.config_path)
```

---

### 2.4 扩展快照后缀与修复 V3 触发器 (`MCP-BUG-4`、`MCP-BUG-5`)

1. **快照后缀扩展**（[`src/godot_mcp/verify_shell/snapshot.py:14`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_shell/snapshot.py#L14)）：

```python
SNAPSHOT_SUFFIXES = {".gd", ".gdshader", ".shader", ".tres", ".tscn", ".uid", ".godot"}
```

2. **支持 `@tool class_name` 同行声明**（[`src/godot_mcp/verify_shell/trigger.py:18`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_shell/trigger.py#L18) 与 [`src/godot_mcp/verify_shell/class_cache.py:15`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_shell/class_cache.py#L15)）：

```python
_CLASS_NAME_RE = re.compile(r"^(?:@tool\s+)?class_name\s+(\S+)", re.MULTILINE)
```

3. **记录 `UID_DUPLICATE` 的雙侧路径**（[`src/godot_mcp/verify_filter/uid_cluster.py:70`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_filter/uid_cluster.py#L70) 与 [`src/godot_mcp/verify_shell/trigger.py:34`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_shell/trigger.py#L34)）：
   - 在 `uid_cluster.py:70` 构造 `UID_DUPLICATE` 的 `ConditionalSignalEvent` 时，将 `target_res_path=max(path_a, path_b)` 填入（当前为 `None`）。
   - 在 `trigger.py:34` 的 `is_uid_duplicate_repair` 中同时匹配 `event.res_path` 与 `event.target_res_path`：

```python
    for event in prev_conditional_events:
        if event.kind == "UID_DUPLICATE":
            candidate_paths = {p for p in (event.res_path, event.target_res_path) if p}
            if candidate_paths & norm_touched:
                return True
```

---

### 2.5 移除 `RedisStateStore` 并更新文档 (`MCP-CLN-1`)

1. 从 [`src/godot_mcp/verify_gate/state_store.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_gate/state_store.py) 与 [`src/godot_mcp/verify_gate/__init__.py`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/src/godot_mcp/verify_gate/__init__.py) 中移除 `RedisStateStore`（以及 `tests/test_verify_gate.py` 中测试 `RedisStateStore` 抛 `NotImplementedError` 的用例）。
2. 更新 [`README.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/README.md) 与 [`ARCHITECTURE.md`](file:///Users/yy_catmax/.gemini/antigravity/worktrees/godot3_to_4_migration_agent/w-1_md_2_md/codebase_index/godot_mcp/ARCHITECTURE.md)，将其中“当前只有 `run_verify` 占位实现”的过期描述更新为实际的四阶段流水线说明。

---

## 3. 验证要求

在 `codebase_index/godot_mcp/` 下执行测试：

```bash
uv run pytest
```

确保全部单测通过。
