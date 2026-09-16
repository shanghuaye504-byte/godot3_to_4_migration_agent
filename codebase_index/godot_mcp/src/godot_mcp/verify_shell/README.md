# verify_shell — 外壳编排

本目录是过滤器（`verify_filter/`）和重试门（`verify_gate/`）之间的一层：决定**这一轮按什么顺序跑 V1/V2/V3**，以及入队拒收、UID 规范化、工作区锁。

权威规格：`docs/verifier_filter_scheme.md` §2.1 / §12。就地说明与手测顺序见 `docs/shell_walkthrough.md`。

| 文件 | 副作用 | 职责 |
| --- | --- | --- |
| `cache.py` | 无 | `.godot/global_script_class_cache.cfg` 是否存在 |
| `class_cache.py` | 无 | 扫磁盘 `class_name`、解析 cache 对象块、判定是否陈旧（不调 `scan_workspace`） |
| `check_file_annotate.py` | 无 | `check_file` 在 filter/merge 后的 A/B 外壳标注；`check_workspace` 不调用 |
| `reject.py` | 无 | 发现 `.csproj` / `.gdextension` 则拒收 |
| `uid.py` | 删工作区 `*.uid` | 入队规范化（不碰 `.godot/`、不 `git rm`） |
| `lock.py` | flock | 同一项目串行 verify |
| `diff.py` | 无 | 解析 unified diff |
| `snapshot.py` | 无 | 扫描工作区源码、相对上一轮快照拼 git 风 diff；相关后缀超 2000 个文件或 1 GiB 则 `SnapshotTooLargeError` |
| `trigger.py` | 无 | `should_run_v3(phase=intake\|iteration\|final_gate)` |
| `collect.py` | 通过注入的 `spawn` 起 Godot | V3 → V1↔V2 循环 → 收尾门 V3 |

对外入口：`collect_workspace_view(...)`。MCP / Gate 胶水仍在 `verify_gate/tool.py`。
Agent 看到的 MCP 字段级契约见 [`docs/mcp_verify_tool_interface.md`](../../../docs/mcp_verify_tool_interface.md)。
