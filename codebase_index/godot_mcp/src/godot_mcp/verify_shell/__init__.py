"""verify_shell —— 过滤器与 Gate 之间的外壳编排。

方案文档：`verifier_filter_scheme.md` §2.1 / §12。本包负责「何时跑哪条命令」：
缓存不变量、入队拒收、UID 规范化、工作区锁、V3 懒触发、V1↔V2 收敛、收尾门。

不起 Godot 的叶子模块（可单独测）：
- `cache` / `reject` / `uid` / `lock` / `diff` / `snapshot` / `trigger`

会起 Godot 的编排：
- `collect.collect_workspace_view`（通过注入的 `spawn`，测试里 mock）
"""

from __future__ import annotations

from godot_mcp.verify_shell.cache import cache_is_warm
from godot_mcp.verify_shell.collect import CollectionResult, collect_workspace_view
from godot_mcp.verify_shell.diff import DiffView, parse_unified_diff
from godot_mcp.verify_shell.lock import WorkspaceBusyError, workspace_lock
from godot_mcp.verify_shell.snapshot import diff_snapshots, scan_workspace
from godot_mcp.verify_shell.reject import UnsupportedProjectError, find_unsupported_files
from godot_mcp.verify_shell.trigger import should_run_v3
from godot_mcp.verify_shell.uid import wipe_uid_sidecars

__all__ = [
    "cache_is_warm",
    "collect_workspace_view",
    "CollectionResult",
    "DiffView",
    "parse_unified_diff",
    "scan_workspace",
    "diff_snapshots",
    "workspace_lock",
    "WorkspaceBusyError",
    "UnsupportedProjectError",
    "find_unsupported_files",
    "should_run_v3",
    "wipe_uid_sidecars",
]
