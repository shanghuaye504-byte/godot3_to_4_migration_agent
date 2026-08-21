"""stability：纵向重复稳定性 + 横向跨 fixture diff。覆盖 N09。

纵向（同一 step 内多个 repeat）：local_signature 集合是否一致、顺序是否一致
——用于发现"非确定性内容"和"非确定性顺序"，以及需要被归一化的随机字段
（内存地址/随机 id/耗时）。

横向（WARM 下相同 command，跨 CleanControl / NP-CASCADE 两个 group 离线 diff）：
只在 local_signature 层面比较——差异字段（res:// 路径、符号名、行号）必须在
noise_signature 里被占位符化，但在 local_signature 里保留，否则 BG 减法会
把不同项目的不同错误错误地折叠成同一个噪声桶（README §0.4.2 的陷阱）。

聚合策略：report_variance（不是 all_equal_required——纵向出现分歧本身就是
一条有效发现，不应该被当成失败拦掉）。
"""

from __future__ import annotations

from .base import Evaluation, register
from .normalize import compute_signatures, parse_output_lines


def _signatures_for_result(raw, rules) -> list:
    lines = parse_output_lines(raw.stdout) + parse_output_lines(raw.stderr)
    return compute_signatures(lines, rules)


def evaluate_vertical(results: list, rules) -> dict:
    if not results:
        return {"status": "NO_DATA"}

    per_repeat_ordered = []
    for raw in results:
        sigs = _signatures_for_result(raw, rules)
        per_repeat_ordered.append([s["local_signature"] for s in sigs])

    per_repeat_sets = [set(order) for order in per_repeat_ordered]
    content_deterministic = all(s == per_repeat_sets[0] for s in per_repeat_sets[1:])
    order_deterministic = all(o == per_repeat_ordered[0] for o in per_repeat_ordered[1:])

    return {
        "status": "OK",
        "repeats": len(results),
        "content_deterministic": content_deterministic,
        "order_deterministic": order_deterministic,
        "signature_sets": [sorted(s) for s in per_repeat_sets],
    }


def evaluate_horizontal(results_by_group: dict, rules) -> dict:
    groups = sorted(results_by_group)
    if len(groups) < 2:
        return {"status": "NO_DATA", "reason": "需要至少两个 group 才能横向对比"}

    per_group_local: dict = {}
    per_group_noise: dict = {}
    for group_id, raws in results_by_group.items():
        local_sigs: set = set()
        noise_sigs: set = set()
        for raw in raws:
            for sig in _signatures_for_result(raw, rules):
                local_sigs.add(sig["local_signature"])
                noise_sigs.add(sig["noise_signature"])
        per_group_local[group_id] = local_sigs
        per_group_noise[group_id] = noise_sigs

    a, b = groups[0], groups[1]
    return {
        "status": "OK",
        "groups": groups,
        "local_signature_only_in": {
            a: sorted(per_group_local[a] - per_group_local[b]),
            b: sorted(per_group_local[b] - per_group_local[a]),
        },
        "noise_signature_shared_count": len(per_group_noise[a] & per_group_noise[b]),
    }


def evaluate(*, vertical_by_step: dict = None, horizontal_by_group: dict = None, **_ignored) -> Evaluation:
    return Evaluation(
        status="OK",
        aggregation="report_variance",
        details={
            "vertical": vertical_by_step or {},
            "horizontal": horizontal_by_group or {},
        },
    )


register("stability", evaluate)
