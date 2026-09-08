"""R5 UID 重复簇压缩 —— 方案文档 §7.6。

仅当 stderr 中存在：

```text
WARNING: UID duplicate detected between res://A and res://B.
```

则在该 WARNING 之后、下一条非 UID 相关事件之前，把下列 ERROR 标为 `cluster_member`：
- `Parse Error: Busy. [Resource file res://A|B:…]`
- `Failed loading resource: res://A|B.`

压缩成 **一条** root_cause：

```text
kind = resource_error
symbol = None
res_path = 字典序较小的那条路径
message = "UID duplicate detected between res://A and res://B."
role = root_cause
cluster_id = local_signature(of the warning template + sorted(A,B))
```

N06：后面 ERROR 数量是严重度假阳性，实质是同一个问题；删掉两个场景的 UID 再 V3
即可，不要让 Agent 去修 `Busy`。

单独伪造 UID、没有 duplicate WARNING 时：探针确认 V1/V2/V3 **全静默**，过滤器无事可做
——这是已声明的盲区（`verifier_filter_scheme.md` §2.1.4 的"入队 UID 规范化"负责兜底，
不是本规则）。
"""

from __future__ import annotations

import re
from dataclasses import replace

from godot_mcp.verify_filter import signature as _sig
from godot_mcp.verify_filter.models import ClassifiedEvent

_UID_DUPLICATE_RE = re.compile(r"UID duplicate detected between (?P<a>res://\S+) and (?P<b>res://\S+)\.")


def apply_uid_cluster_rule(events: list[ClassifiedEvent]) -> list[ClassifiedEvent]:
    """把 UID duplicate WARNING 及其伴随的 Busy/Failed loading ERROR 压缩成一条 root_cause。"""
    result: list[ClassifiedEvent] = []
    n = len(events)
    i = 0
    while i < n:
        event = events[i]
        match = _UID_DUPLICATE_RE.search(event.message) if event.kind == "warning" else None

        if match is None:
            result.append(event)
            i += 1
            continue

        path_a, path_b = match.group("a"), match.group("b")
        relevant_paths = {path_a, path_b}

        j = i + 1
        members: list[ClassifiedEvent] = []
        while j < n:
            candidate = events[j]
            if candidate.kind == "resource_error" and candidate.res_path in relevant_paths:
                members.append(candidate)
                j += 1
                continue
            break  # 遇到第一个不相关事件（如 debugger plugin 行）就停止扫描

        cluster_res_path = min(path_a, path_b)
        message = f"UID duplicate detected between {path_a} and {path_b}."
        normalized = _sig.normalize_message(message)
        template = _sig.msg_template(normalized)
        cluster_id = _sig.local_signature(
            kind="resource_error",
            res_path=cluster_res_path,
            symbol=None,
            normalized_message=normalized,
        )

        merged_root_cause = ClassifiedEvent(
            prefix="WARNING",
            message=message,
            at_function=event.at_function,
            at_location=event.at_location,
            res_path=cluster_res_path,
            target_res_path=None,
            line_in_project=None,
            engine_location=event.engine_location,
            source_stream=event.source_stream,
            raw_block=event.raw_block,
            kind="resource_error",
            symbol=None,
            msg_template=template,
            local_signature=cluster_id,
            noise_signature=_sig.noise_signature(kind="resource_error", template=template),
            role="root_cause",
            cluster_id=cluster_id,
        )
        result.append(merged_root_cause)
        for member in members:
            result.append(replace(member, role="cluster_member", cluster_id=cluster_id, drop_reason="uid_duplicate_satellite"))

        i = j  # 跳过已经消化的成员事件
    return result
