"""R4 `Failed to load script` 包装行 —— 方案文档 §7.5（含窄"升级例外"）。

包装行的 `res_path` 取 message 里的脚本路径（与 `at:` 引擎路径无关）——`parse.py`
已经从 message 里抽好了，本规则直接读 `event.res_path`。

```text
message 匹配 Failed to load script "res://..." with error "Parse error|Compilation failed"
→ role=symptom, drop_reason=failed_to_load_wrapper
```

它几乎总是紧跟一条 SCRIPT ERROR；reward 只保留上面的 SCRIPT ERROR。

**若 SCRIPT ERROR 已被 R2 删掉（autoload FP），包装也删，禁止升级成根因。** 样例 A
滤掉 Config 之后恰好只剩包装；若升级，T-A 会失败，等于把 FP 送回 reward。

**升级例外（窄）**：只看**解析完成、过滤开始之前**的事件集。当且仅当该 `res_path`
在原始解析结果里**从未出现过任何 SCRIPT ERROR**（引擎只打了包装、没有正文）时，才把
包装升为 `root_cause`。因 FP / 症状被删而变空的，不升级。4.7.1 探针未出现"只有包装"
形态；用合成样例锁住例外，用 T-A 锁住"不得因 R2 升级"。
"""

from __future__ import annotations

import re
from dataclasses import replace

from godot_mcp.verify_filter.models import ClassifiedEvent

_WRAPPER_RE = re.compile(
    r'Failed to load script "(?P<path>res://[^"]+)" with error "(?:Parse error|Compilation failed)"\.'
)


def apply_wrapper_rule(
    events: list[ClassifiedEvent],
    *,
    original_events_by_res_path: dict[str, list[ClassifiedEvent]],
) -> list[ClassifiedEvent]:
    """标记 `Failed to load script` 包装行为 `symptom`；仅在窄升级例外条件下升为 `root_cause`。

    `original_events_by_res_path` 是**解析完成、任何过滤规则介入之前**按 `res_path`
    分组的事件快照（调用方在 `pipeline.py` 里，`classify()` 刚跑完时构建），用来判断
    "这个文件从一开始就没有 SCRIPT ERROR"，不能用过滤中途的集合代替（否则会把"被 R2
    删空"误判成"从来没有"）。
    """
    result: list[ClassifiedEvent] = []
    for event in events:
        if event.role == "false_positive":
            # R1（哨兵）已经处理过，跳过。
            result.append(event)
            continue

        if event.kind == "resource_error" and _WRAPPER_RE.search(event.message):
            originals = original_events_by_res_path.get(event.res_path or "", [])
            had_script_error = any(orig.prefix == "SCRIPT ERROR" for orig in originals)
            if had_script_error:
                result.append(replace(event, role="symptom", drop_reason="failed_to_load_wrapper"))
            else:
                # 窄升级例外：这个文件从解析完成的那一刻起就没有任何 SCRIPT ERROR 正文。
                result.append(replace(event, role="root_cause", drop_reason=None))
        else:
            result.append(event)
    return result
