"""R7 warning 与终止条件 —— 方案文档 §7.8。

补齐说明：此前的文件布局（方案文档 §13）只列了 R1–R6 对应的文件，R7 漏了，这里补上。

`prefix == WARNING` 的事件：
- 若已被 R5（`uid_cluster.py`）提升为 UID 簇根，保留为 `root_cause`（唯一例外：文案是
  WARNING，但 N06 确认它代表真实的、会让 import 失败的问题）。
- 其余 WARNING：`role` 保持信息性，**不进入** `root_cause_errors`，
  `drop_reason="warning_not_in_reward"`。

N05：默认与注入 warning 开关后 CLI 都收集不到普通 GDScript warning；不要为实现
"第二档信号"去开 `--debug`（N08 已确认 `--debug` 会 signal 11 崩溃）。

实现说明：如何区分"已被 R5 提升的簇根"与"尚未处理的普通 WARNING"——两者 `prefix`
都是 `"WARNING"`，`role` 也都可能是 `"root_cause"`（簇根是 R5 显式设的；普通 WARNING
是 `classify()` 的中性默认值，尚未被任何规则处理）。唯一可靠的区分标记是
`cluster_id`：R5 会给簇根事件设置一个非 `None` 的 `cluster_id`，普通未处理的 WARNING
则是 `None`。本规则据此 skip 已被 R5 处理过的事件。
"""

from __future__ import annotations

from dataclasses import replace

from godot_mcp.verify_filter.models import ClassifiedEvent


def apply_warning_downgrade_rule(events: list[ClassifiedEvent]) -> list[ClassifiedEvent]:
    """把非 UID-簇根的 WARNING 标记为 `drop_reason="warning_not_in_reward"`，不改变 `role`。

    注意本规则不删除事件（WARNING 仍保留在结果里作为信息性数据），只是通过
    `drop_reason` 标记它不参与 `status`/`root_cause_errors` 的判断——由 `pipeline.py`
    在组装 `FilterResult` 时据此把它排除出 `root_cause_errors`。
    """
    result: list[ClassifiedEvent] = []
    for event in events:
        if event.prefix == "WARNING" and event.cluster_id is None:
            result.append(replace(event, drop_reason="warning_not_in_reward"))
        else:
            result.append(event)
    return result
