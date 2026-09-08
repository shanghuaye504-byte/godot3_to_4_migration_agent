"""R1 哨兵人造边 —— 方案文档 §7.2。

```text
若 res_path 以 __probe_ 为文件名前缀，或 res_path ∈ sentinel_res_paths，则：
  - Compile Error: Failed to compile depended scripts → drop, sentinel_artifact
  - Failed to load script "res://__probe_sentinel.gd" → drop, sentinel_artifact
  - Parse Error: Could not preload/resolve 且 at 在哨兵上
        → role=pointer（不要 drop）
        → target_res_path = message 里的 res://X.gd（V2 只跑这个，不要跑哨兵）
```

依据：N01"哨兵 compile error 一定对应前面已经打出的其它脚本错误"；N04"V1 只点到
哨兵直接 preload 的根，文案是 Could not preload/resolve，不是真实语法"。

实现说明：`parse.py` 已经把 pointer 事件的 `target_res_path` 从 message 里抽好了，
不管 `res_path`（引用方）是不是哨兵——所以本规则遇到哨兵上的 pointer 事件时什么都
不用做（原样保留即可），只需要处理"哨兵自身产生的症状/包装行"这两类需要 drop 的情况。
"""

from __future__ import annotations

from dataclasses import replace

from godot_mcp.verify_filter.models import ClassifiedEvent


def _is_sentinel_path(res_path: str | None, sentinel_res_paths: frozenset[str]) -> bool:
    if res_path is None:
        return False
    if res_path in sentinel_res_paths:
        return True
    basename = res_path.rsplit("/", 1)[-1]
    return basename.startswith("__probe_")


def apply_sentinel_rule(
    events: list[ClassifiedEvent],
    *,
    sentinel_res_paths: frozenset[str],
) -> list[ClassifiedEvent]:
    """处理哨兵自身产生的人造级联边；`protected`/`pointer` 事件必须原样跳过。"""
    result: list[ClassifiedEvent] = []
    for event in events:
        if event.role in ("protected", "pointer", "false_positive"):
            result.append(event)
            continue

        if _is_sentinel_path(event.res_path, sentinel_res_paths) and event.kind in (
            "compile_error",
            "resource_error",
        ):
            result.append(replace(event, role="false_positive", drop_reason="sentinel_artifact"))
        else:
            result.append(event)
    return result
