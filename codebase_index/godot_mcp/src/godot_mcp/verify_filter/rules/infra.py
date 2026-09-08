"""R6 调试器插件噪声 —— 方案文档 §7.7。

```text
message == "Plugin is not attached to debugger."
→ role=infra_noise, drop_reason=debugger_plugin_detached
```

N06 在 UID 重复的 V3 日志末尾稳定出现，与脚本对错无关，不要当插件坏了处理。

实现说明：`classify()`（`parse.py`）已经把这条消息的默认 `role` 判成
`"infra_noise"`（§5.2 表格本身就是这么定的，不是"候选"），本规则只补上 `drop_reason`，
不需要重新判断一次文案。
"""

from __future__ import annotations

from dataclasses import replace

from godot_mcp.verify_filter.models import ClassifiedEvent

_DEBUGGER_PLUGIN_MESSAGE = "Plugin is not attached to debugger."


def apply_debugger_plugin_rule(events: list[ClassifiedEvent]) -> list[ClassifiedEvent]:
    """把 `Plugin is not attached to debugger.` 标记为 `infra_noise` 并 drop。"""
    result: list[ClassifiedEvent] = []
    for event in events:
        if event.role == "infra_noise" and event.message == _DEBUGGER_PLUGIN_MESSAGE:
            result.append(replace(event, drop_reason="debugger_plugin_detached"))
        else:
            result.append(event)
    return result
