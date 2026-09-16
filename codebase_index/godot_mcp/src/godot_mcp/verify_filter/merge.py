"""跨命令聚合 —— 方案文档 §7.10 与 §7.10.1（原 R8，不在单次流水线里）。

`filter_verify_output` 只吃一份 stdout/stderr，看不见"后来那次 V2"。V1 与多次 V2（可选
再加一次 V3）的合并是**第二个纯函数**，由外壳在跑完一轮采集后调用。

多次调用契约（方案文档 §7.10 补齐段）：本函数在一轮 verify 内部**可能被反复调用**——
外壳的判定伪代码是「V1 → 对 pointer 跑 V2 → merge → 若 pointer 集仍在变，再 V1」，直到
收敛或达到 `collect.MAX_V1_ROUNDS`。每次调用时 `v2_by_target` 是累积增长的，`v1` 用最新一次的
`FilterResult` 替换。**只有收敛之后的最后一次返回值，才是这一 round 要交给下游
Verify Gate 的 `ProjectFilterView`**——这也是 `verifier_retry_gate_scheme.md` §2.2.4
"一次 Gate 调用 = 一个 round"粒度契约的前提，两份文档共用同一条口径。

`merge_command_results` 的参数语义、三分支和探针出处（N04 / N08 / N01 / N02 / N07 / N09）
写在函数 docstring 与循环内注释里；对照笔记见同目录 `docs/merge_walkthrough.md`。
"""

from __future__ import annotations

from typing import Iterable

from godot_mcp.verify_filter.models import ClassifiedEvent, FilterResult, ProjectFilterView


def merge_command_results(
    v1: FilterResult,
    v2_by_target: dict[str, FilterResult],
    v3: FilterResult | None = None,
) -> ProjectFilterView:
    """把「可能带 pointer 的主结果」和「按文件下钻的 V2」合成一张项目视图。

    参数名按合并角色起，不强制第一份日志来自 V1 命令：
    - ``v1``：主结果。工作区路径里通常是哨兵 V1（pointer 最多）。
      ``check_file`` 只跑了一次 V2、没有下钻时，把那份 V2 放这里、``v2_by_target`` 传 ``{}``，
      只做 FilterResult → ProjectFilterView 升格。
    - ``v2_by_target``：已经对某些文件跑过 V2。key 必须是 pointer 的 ``target_res_path``
      （坏文件），不是引用方 ``res_path``。N04 实测用错会永远对 ``dep_1.gd`` 跑 V2，
      真正的 ``root_bad.gd`` 永远查不到。
    - ``v3``：本轮是否跑过 import。有则 ``shader_checked=True``；没有则写
      ``shader_not_checked``（N07：V1/V2 看不见 shader，单次 filter 不知道有没有 V3）。

    设计来自哪些探针、为什么必须这样合并：

    - **N04（级联 / pointer）**：V1 报不全、也不报具体语法，只打出
      ``Could not preload/resolve "res://B.gd"``。不 V2(B) 就看不到 ``Unexpected Indent``。
      pointer 和 V2 根因是同一问题的两面，合并时只能留一面，否则 Gate 重试计数翻倍、误熔断。
      样例 F 单次 V2 仍会带 pointer——没下钻就不能假装项目扫完。
    - **N08**：``--check-only`` 退出码不可信；启动成功 ≠ 脚本正确。空日志只表示
      「这份 stderr 没有可进 reward 的行」，不是「文件已证明干净」。
    - **N01 / N02（autoload / addon 假阳性 + 编译截断）**：R2 会删
      ``Identifier not found: Config``。同文件后面若是 Compile Error，引擎常被挡住、
      日志里根本没有那一行。V2 根因为空时丢掉 pointer 却不标 ``untrusted``，会把
      「过滤后没剩根因」说成「迁移完成」。N02 补实验要求：用 ``untrusted_files`` 声明
      FN，不要假装没有。
    - **N07**：shader 只在 V3 可见。``shader_checked`` 只看本函数有没有收到 ``v3``，
      不由单次 filter 猜测。

    对 ``v1.pointers`` 每条「A 编不过是因为 preload 不了 B」：
    - B 还不在字典里 → 留在 ``pending_pointers``，项目级未完成（即使各次 status 都 CLEAN）。
    - V2(B) 有根因 → 丢掉 pointer，根因只从 V2 计一次。
    - V2(B) 根因为空（CLEAN 或只剩被滤掉的 FP）→ 丢掉 pointer，B 记入 ``untrusted_files``。

    根因 / 症状 / dropped：把 v1、所有 V2、可选 V3 拼起来，按 ``local_signature`` 去重（N09）。
    ``gdscript_complete`` = 没有根因 **且** 没有未下钻 pointer。完成 ≠ 信任：
    ``untrusted_files`` 非空也不把 status 改成 HAS_ERRORS（方案文档 §4 / §9）。
    """
    pending_pointers: list[ClassifiedEvent] = []
    extra_untrusted: set[str] = set()

    for pointer in v1.pointers:
        target = pointer.target_res_path
        # N04：还没对 target 跑 V2（或 pointer 抽不出路径）→ 不能当已 drill-down。
        # 样例 F 就是「单次 CLEAN + 一条 pointer」；悄悄丢掉会让 gdscript_complete 假成真。
        if target is None or target not in v2_by_target:
            pending_pointers.append(pointer)
            continue

        v2_result = v2_by_target[target]
        if v2_result.root_cause_errors:
            # N04：V2 已经打出 B 的真语法/编译根因。pointer 只是「去打 B」的路标，
            # 再留着会和 root_cause_errors 各计一次，症状进 retry → 误触发熔断。
            continue

        # N01/N02 + N08：V2(B) 交了白卷。
        # 可能是 R2 把 autoload FP 删光（编译截断，后面的 Compile Error 从未打出），
        # 也可能是空 stderr（check-only 漏报，或 pointer 本身是级联误报）。
        # pointer 必须丢掉，否则外壳会对 B 无限 V2；但不能把 B 签成「已证明干净」。
        extra_untrusted.add(target)

    all_results = [v1, *v2_by_target.values()]
    if v3 is not None:
        all_results.append(v3)

    root_cause_errors = _dedupe_events(r for result in all_results for r in result.root_cause_errors)
    symptoms = _dedupe_events(r for result in all_results for r in result.symptoms)
    dropped = _dedupe_events(r for result in all_results for r in result.dropped)

    # R2 标的是「这份日志里谁被截断」（引用方）；上面 extra 标的是「V1 指控过、V2 交白卷的 B」。
    untrusted_files = frozenset(extra_untrusted).union(*(result.untrusted_files for result in all_results))

    caveats: list[str] = []
    seen_caveats: set[str] = set()
    for result in all_results:
        for caveat in result.caveats:
            if caveat not in seen_caveats:
                seen_caveats.add(caveat)
                caveats.append(caveat)
    # N07：V1/V2 对 .gdshader 是盲区。单次 filter 不知道本轮有没有 V3，必须由本函数写。
    if v3 is None and "shader_not_checked" not in seen_caveats:
        caveats.append("shader_not_checked")

    # 公式见方案文档 §7.10.1：pointer 消化完 ≠ 项目干净（根因可能还在 V2 里）。
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
    """按 `local_signature` 去重，保留第一次出现的顺序。

    V1 pointer 消化后，同一根因可能同时出现在 V1 包装行和 V2 正文里。N09 确认
    归一化后签名跨 repeat 稳定，所以跨命令也只认这一字段。
    """
    seen: set[str] = set()
    result: list[ClassifiedEvent] = []
    for event in events:
        if event.local_signature in seen:
            continue
        seen.add(event.local_signature)
        result.append(event)
    return result
