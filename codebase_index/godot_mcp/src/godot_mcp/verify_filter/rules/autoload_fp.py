"""R2 autoload / addon 假阳性 —— 方案文档 §7.3（核心规则）。

白名单来源：只解析 `project.godot` 的 `[autoload]` 段 key（`autoload.py`），不扫
addon 源码里的 `add_autoload_singleton` 调用（N02 确认没必要，且更贵更不可靠）。

只删这一类行：

```text
prefix == SCRIPT ERROR
message 精确匹配  Compile Error: Identifier not found: {KEY}
KEY ∈ autoload_keys
且 role 不是 protected
```

然后：
1. `role=false_positive`，`drop_reason=autoload_identifier_fp`。
2. 该事件的 `res_path` 加入 `untrusted_files`（外壳/pipeline 层汇总），caveat 写
   `compile_truncated:{res_path}`。
3. **不要**因为本文件只剩这条 FP，就把文件或项目标成"已证明干净"。
4. **不要**用 V5 决定删不删。
5. **不要**删 `Parse Error: Identifier "X" not declared...`，即使 X 碰巧等于某个
   autoload key（`kind` 不是 `compile_error`，天然不会命中本规则的判断条件）。
6. **不要**删 `Identifier not found: X` 当 X 不在 `autoload_keys` 里——那是真缺失。

编译截断事实（N02 补实验）：同文件后面若是 Parse Error，引擎仍会打出，删 Config 行
不会让它们消失；同文件后面若是 Compile Error，引擎常被 Config 挡住，日志里可能只剩
Identifier-not-found——这是 FN，用 `untrusted_files` 声明，不要假装没有。
"""

from __future__ import annotations

from dataclasses import replace

from godot_mcp.verify_filter.models import ClassifiedEvent


def apply_autoload_fp_rule(
    events: list[ClassifiedEvent],
    *,
    autoload_keys: frozenset[str],
) -> tuple[list[ClassifiedEvent], frozenset[str], list[str]]:
    """返回 (处理后的事件列表, 新增的 untrusted_files, 新增的 caveats)。

    `autoload_keys` 为空集时（插件未启用/无 autoload）本规则不删任何事件——这是
    正确行为，不是漏过滤（方案文档 §8 末尾）。
    """
    result: list[ClassifiedEvent] = []
    untrusted: set[str] = set()
    caveats: list[str] = []

    for event in events:
        is_candidate = (
            event.prefix == "SCRIPT ERROR"
            and event.kind == "compile_error"
            and event.role not in ("protected", "false_positive")
            and event.symbol is not None
            and event.symbol in autoload_keys
            and event.message == f"Compile Error: Identifier not found: {event.symbol}"
        )
        if is_candidate:
            result.append(replace(event, role="false_positive", drop_reason="autoload_identifier_fp"))
            if event.res_path:
                untrusted.add(event.res_path)
                caveats.append(f"compile_truncated:{event.res_path}")
        else:
            result.append(event)

    return result, frozenset(untrusted), caveats
