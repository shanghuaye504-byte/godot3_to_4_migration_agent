"""流水线编排 —— 方案文档 §7（只编排 §7.1–§7.8，不含 §7.10 的跨命令合并，那是 `merge.py`）。

顺序固定，禁止重排（§7 开头）：

```text
parse
  → classify inner message（§5.2 默认 role）
  → 标记 protected（§7.1，rules/protect.py）
  → R1 哨兵人造边（rules/sentinel.py）
  → R2 autoload / addon Identifier-not-found FP（rules/autoload_fp.py）
  → R3 depended-scripts 症状（rules/cascade.py）
  → R4 Failed-to-load 包装行（rules/wrappers.py）
  → R5 UID 重复簇压缩（rules/uid_cluster.py）
  → R6 debugger plugin 噪声（rules/infra.py）
  → R7 warning 降级（rules/warning.py）
  → R8 按 local_signature 去重（本文件，§7.9，不拆单独规则文件）
  → 组装 FilterResult
```

后一条规则看到的是前一条 `replace()` 过 `role` 的事件集合（models.py 的注解）。不要
把 §7.10 的 `merge_command_results` 逻辑写进这里——它需要多份命令的结果，属于另一个
纯函数，见方案文档 §1"过滤器不启动 V3""filter_verify_output 只吃一份 stdout/stderr"。
"""

from __future__ import annotations

from godot_mcp.verify_filter.models import ClassifiedEvent, CommandKind, FilterResult
from godot_mcp.verify_filter.parse import classify, parse_raw_events
from godot_mcp.verify_filter.rules.autoload_fp import apply_autoload_fp_rule
from godot_mcp.verify_filter.rules.cascade import apply_cascade_symptom_rule
from godot_mcp.verify_filter.rules.infra import apply_debugger_plugin_rule
from godot_mcp.verify_filter.rules.protect import mark_protected
from godot_mcp.verify_filter.rules.sentinel import apply_sentinel_rule
from godot_mcp.verify_filter.rules.uid_cluster import apply_uid_cluster_rule
from godot_mcp.verify_filter.rules.warning import apply_warning_downgrade_rule
from godot_mcp.verify_filter.rules.wrappers import apply_wrapper_rule

_DEFAULT_SENTINEL_RES_PATHS: frozenset[str] = frozenset({"res://__probe_sentinel.gd"})


def filter_verify_output(
    raw_stdout: str,
    raw_stderr: str,
    *,
    command: CommandKind,
    autoload_keys: frozenset[str],
    sentinel_res_paths: frozenset[str] = _DEFAULT_SENTINEL_RES_PATHS,
) -> FilterResult:
    """单次命令、单份日志的过滤入口（方案文档 §1）。纯函数：无 IO、无 Godot 子进程。

    `autoload_keys` 由调用方通过 `parse_autoload_keys(project_godot_text)` 得到，
    再传进来——本函数不读取 `project.godot`，也不知道它在哪里。

    `command` 目前只影响下游对结果的解读方式（§9 的"各命令下过滤器的预期行为"表），
    不在本函数内部改变过滤规则的执行顺序。
    """
    del command  # 仅供下游（merge.py/外壳）解读用，本函数内部不分支

    raw_events = parse_raw_events(raw_stdout, raw_stderr)
    classified = classify(raw_events)

    # R4 的窄升级例外需要"解析完成、任何规则介入之前"的快照，必须在这里存一份，
    # 不能等后面规则跑完再补拍——那时候"从来没有"和"被删空"已经无法区分。
    original_by_res_path: dict[str, list[ClassifiedEvent]] = {}
    for event in classified:
        if event.res_path:
            original_by_res_path.setdefault(event.res_path, []).append(event)

    events = mark_protected(classified)
    events = apply_sentinel_rule(events, sentinel_res_paths=sentinel_res_paths)
    events, r2_untrusted, r2_caveats = apply_autoload_fp_rule(events, autoload_keys=autoload_keys)
    events = apply_cascade_symptom_rule(events)
    events = apply_wrapper_rule(events, original_events_by_res_path=original_by_res_path)
    events = apply_uid_cluster_rule(events)
    events = apply_debugger_plugin_rule(events)
    events = apply_warning_downgrade_rule(events)

    deduped = _dedupe_by_local_signature(events)

    root_cause_errors: list[ClassifiedEvent] = []
    pointers: list[ClassifiedEvent] = []
    symptoms: list[ClassifiedEvent] = []
    dropped: list[ClassifiedEvent] = []
    for event in deduped:
        if event.role in ("root_cause", "protected") and event.drop_reason is None:
            root_cause_errors.append(event)
        elif event.role == "pointer":
            pointers.append(event)
        elif event.role == "symptom":
            symptoms.append(event)
        else:
            dropped.append(event)

    status = "HAS_ERRORS" if root_cause_errors else "CLEAN"

    return FilterResult(
        status=status,
        root_cause_errors=sorted(root_cause_errors, key=lambda e: e.local_signature),
        pointers=pointers,
        symptoms=symptoms,
        dropped=dropped,
        caveats=list(r2_caveats),
        untrusted_files=r2_untrusted,
    )


def _dedupe_by_local_signature(events: list[ClassifiedEvent]) -> list[ClassifiedEvent]:
    """§7.9：同一 `local_signature` 只留第一次出现的事件；结果按 `local_signature` 排序。

    同一 `target_res_path` 上成对的 `Could not preload` 与 `Could not resolve` 在这一步
    合并为一条 pointer，不是两条——两者文案不同、`local_signature` 天然不同，所以第一遍
    按签名去重"合并"不了它们，需要专门再对 pointer 角色按 `target_res_path` 去重一次。
    """
    seen_signatures: set[str] = set()
    first_pass: list[ClassifiedEvent] = []
    for event in events:
        if event.local_signature in seen_signatures:
            continue
        seen_signatures.add(event.local_signature)
        first_pass.append(event)

    seen_pointer_targets: set[str] = set()
    result: list[ClassifiedEvent] = []
    for event in first_pass:
        if event.role == "pointer":
            if event.target_res_path in seen_pointer_targets:
                continue
            seen_pointer_targets.add(event.target_res_path or "")
        result.append(event)
    return result
