"""R3 `Failed to compile depended scripts` 症状 —— 方案文档 §7.4。

```text
message == "Compile Error: Failed to compile depended scripts."
→ role=symptom, drop_reason=depended_scripts_compile
```

N04：一级引用只有 preload/resolve，没有这条；二级及以上每层一条。它不描述根因，
禁止进 retry。事件仍放进 `symptoms` 给 LLM 参考（"这个文件依赖链断了"）。

若该行的 `res_path` 是哨兵，R1（`sentinel.py`）已经 drop（`role="false_positive"`），
本规则 skip，不重复处理——这也是为什么下面的判断要排除 `role == "false_positive"`。
"""

from __future__ import annotations

import re
from dataclasses import replace

from godot_mcp.verify_filter.models import ClassifiedEvent

_DEPENDED_SCRIPTS_RE = re.compile(r"Compile Error: Failed to compile depended scripts\.")


def apply_cascade_symptom_rule(events: list[ClassifiedEvent]) -> list[ClassifiedEvent]:
    """把 `Failed to compile depended scripts` 标记为 `symptom`，不进 `root_cause_errors`。"""
    result: list[ClassifiedEvent] = []
    for event in events:
        if event.role == "false_positive":
            # R1 已经把哨兵上的这条消化成 sentinel_artifact，跳过，不重复改写。
            result.append(event)
            continue
        if event.kind == "compile_error" and _DEPENDED_SCRIPTS_RE.search(event.message):
            result.append(replace(event, role="symptom", drop_reason="depended_scripts_compile"))
        else:
            result.append(event)
    return result
