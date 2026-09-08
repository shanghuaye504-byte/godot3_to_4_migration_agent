"""跨命令聚合 —— 方案文档 §7.10 与 §7.10.1（原 R8，不在单次流水线里）。

`filter_verify_output` 只吃一份 stdout/stderr，看不见"后来那次 V2"。V1 与多次 V2（可选
再加一次 V3）的合并是**第二个纯函数**，由外壳在跑完一轮采集后调用。

多次调用契约（方案文档 §7.10 补齐段）：本函数在一轮 verify 内部**可能被反复调用**——
外壳的判定伪代码是「V1 → 对 pointer 跑 V2 → merge → 若 pointer 集仍在变，再 V1」，直到
收敛或达到上限（建议 8）。每次调用时 `v2_by_target` 是累积增长的，`v1` 用最新一次的
`FilterResult` 替换。**只有收敛之后的最后一次返回值，才是这一 round 要交给下游
Verify Gate 的 `ProjectFilterView`**——这也是 `verifier_retry_gate_scheme.md` §2.2.4
"一次 Gate 调用 = 一个 round"粒度契约的前提，两份文档共用同一条口径。
"""

from __future__ import annotations

from typing import Iterable

from godot_mcp.verify_filter.models import ClassifiedEvent, FilterResult, ProjectFilterView


def merge_command_results(
    v1: FilterResult,
    v2_by_target: dict[str, FilterResult],
    v3: FilterResult | None = None,
) -> ProjectFilterView:
    """把 V1 的 pointer 与对应 V2 结果（可选再加一次 V3）合并成项目级视图。

    合并规则（§7.10）：
      S = {p.target_res_path for p in v1.pointers}  # 已扣哨兵 res_path（哨兵上的 pointer
          本身也可能出现在 v1.pointers 里，这里不区分来源，一律按 target_res_path 处理）
      对 S 中每个 target：
        若 target 在 v2_by_target 里且该结果 root_cause_errors 非空
            → 丢弃指向该 target 的 pointer（根因已在 V2 里，避免计两次）
        若 target 在 v2_by_target 里但该结果根因为空（只剩被滤掉的 FP）
            → 丢弃 pointer，把 target 并入 untrusted_files
        若 target 不在 v2_by_target 里
            → pointer 保留在 pending_pointers，项目级未完成

    单次 V2（样例 F）必须仍输出 pointer，本函数不得假装已经 drill-down 完成——这里的
    "假装完成"具体表现为：如果 target 不在 v2_by_target 里，就不能悄悄把它从
    pending_pointers 里去掉。

    派生字段计算（§7.10.1）：
      gdscript_complete = (len(root_cause_errors) == 0) and (len(pending_pointers) == 0)
      shader_checked    = (v3 is not None)
      status            = "HAS_ERRORS" if root_cause_errors else "CLEAN"
      caveats 含 shader_not_checked ⇔ v3 is None（本函数负责写入，不由单次 filter 猜测）
    """
    pending_pointers: list[ClassifiedEvent] = []
    extra_untrusted: set[str] = set()

    for pointer in v1.pointers:
        target = pointer.target_res_path
        if target is None or target not in v2_by_target:
            pending_pointers.append(pointer)
            continue

        v2_result = v2_by_target[target]
        if v2_result.root_cause_errors:
            # 根因已经在对应的 V2 结果里，pointer 本身不再重复计入。
            continue

        # V2 跑过了，但只剩被滤掉的 FP（或本来就是 CLEAN）——target 的编译状态不可信。
        extra_untrusted.add(target)

    all_results = [v1, *v2_by_target.values()]
    if v3 is not None:
        all_results.append(v3)

    root_cause_errors = _dedupe_events(r for result in all_results for r in result.root_cause_errors)
    symptoms = _dedupe_events(r for result in all_results for r in result.symptoms)
    dropped = _dedupe_events(r for result in all_results for r in result.dropped)

    untrusted_files = frozenset(extra_untrusted).union(*(result.untrusted_files for result in all_results))

    caveats: list[str] = []
    seen_caveats: set[str] = set()
    for result in all_results:
        for caveat in result.caveats:
            if caveat not in seen_caveats:
                seen_caveats.add(caveat)
                caveats.append(caveat)
    if v3 is None and "shader_not_checked" not in seen_caveats:
        caveats.append("shader_not_checked")

    gdscript_complete = len(root_cause_errors) == 0 and len(pending_pointers) == 0
    shader_checked = v3 is not None
    status = "HAS_ERRORS" if root_cause_errors else "CLEAN"

    return ProjectFilterView(
        status=status,
        root_cause_errors=root_cause_errors,
        pending_pointers=pending_pointers,
        symptoms=symptoms,
        dropped=dropped,
        caveats=caveats,
        untrusted_files=untrusted_files,
        gdscript_complete=gdscript_complete,
        shader_checked=shader_checked,
    )


def _dedupe_events(events: Iterable[ClassifiedEvent]) -> list[ClassifiedEvent]:
    """按 `local_signature` 去重，保留第一次出现的顺序（多个命令结果可能重复报同一根因）。"""
    seen: set[str] = set()
    result: list[ClassifiedEvent] = []
    for event in events:
        if event.local_signature in seen:
            continue
        seen.add(event.local_signature)
        result.append(event)
    return result
