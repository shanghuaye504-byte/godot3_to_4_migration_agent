"""§7.1 保护名单——先打标，后续规则碰到 `protected` 必须 skip，永远不得改为其它角色。

满足任一即 `role = protected`：

| 条件 | 证据 | 若误删的后果 |
| --- | --- | --- |
| `Parse Error: Class "…" hides an autoload singleton.` | N01 AL-SHADOW | 真命名冲突被当成 FP |
| `Parse Error: Identifier "…" not declared in the current scope.` | N02 补实验 + N03 | 真缺失被删；或把冷缓存问题伪装成"已过滤" |
| 任意 `kind=parse_error` 且不是 §5.2 表中的 pointer 三种文案 | N04 分母、N08 真错 | 语法错误是 reward 本体 |
| `SHADER ERROR:` 前缀 | N07 | 唯一能看见的 shader 根因 |

`Compile Error: Identifier not found: X` **不在**保护名单——它是 R2（`autoload_fp.py`）
的输入，不是本模块的职责。

实现说明：上表前两行本质上都是"`kind=parse_error` 且 `role != pointer`"的特例，
`classify()`（`parse.py`）已经把它们的默认 `kind` 判成 `parse_error`，本函数不需要
重新用正则匹配一遍具体文案，只需要按"`kind=parse_error` 且 `role != pointer`"与
"`prefix=='SHADER ERROR'`"这两条结构性条件判断，就能覆盖上表全部四行，不重复实现
一次 R2 判断（`Identifier not found` 的 `kind` 是 `compile_error`，天然不落进这条规则）。
"""

from __future__ import annotations

from dataclasses import replace

from godot_mcp.verify_filter.models import ClassifiedEvent


def mark_protected(events: list[ClassifiedEvent]) -> list[ClassifiedEvent]:
    """按上表把满足条件的事件 `role` 改为 `"protected"`，其余原样返回。"""
    result: list[ClassifiedEvent] = []
    for event in events:
        is_non_pointer_parse_error = event.kind == "parse_error" and event.role != "pointer"
        is_shader_error = event.prefix == "SHADER ERROR"
        if is_non_pointer_parse_error or is_shader_error:
            result.append(replace(event, role="protected"))
        else:
            result.append(event)
    return result
