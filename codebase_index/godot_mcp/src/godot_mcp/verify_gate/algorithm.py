"""判定算法 —— 方案文档 §2.1/§4。三层关系（方案文档 §1.1）：

```text
Godot 子进程 → 噪声过滤器（纯函数） → Verify Gate（本文件，有状态，确定性代码） → Agent/LLM
```

判定顺序（§4.2，优先级从高到低，一旦命中即返回，不再往下判断）：

```text
1. infra_status != OK 且连续达到 infra_failure_streak_limit  → CIRCUIT_OPEN（硬停止）
2. rounds_used >= rounds_limit 或 cost_used_usd >= cost_limit_usd → BUDGET_EXCEEDED（硬停止）
3. 检测到 A→B→A 震荡（oscillation_window 内）                → OSCILLATION_ESCALATE（硬停止）
4. 连续 no_progress_window 轮签名集合完全相同                  → NO_PROGRESS_WARN（软提示）
5. 存在文件的 patch 次数 >= file_stuck_threshold 且相关签名未变 → FILE_STUCK_WARN（软提示）
6. 否则                                                        → CONTINUE
```

硬停止条件必须排在软提示之前；基础设施熔断排最前，因为 Godot 进程本身跑不起来时，
后面所有基于"签名集合"的判断都建立在不可靠的数据上。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from godot_mcp.verify_gate.config import RetryGateConfig
from godot_mcp.verify_gate.models import (
    BudgetSnapshot,
    GateDecision,
    GateDiff,
    ProjectStatusWithInfra,
    ProjectVerifyState,
    VerifyGateRequest,
    VerifyGateResult,
)

if TYPE_CHECKING:
    from godot_mcp.verify_filter.models import ProjectFilterView

_HARD_STOP: frozenset[GateDecision] = frozenset(
    {"OSCILLATION_ESCALATE", "BUDGET_EXCEEDED", "CIRCUIT_OPEN"}
)

_ROUND_INDEX_DRIFT_HINT = "调用方 round_index 与内部计数不一致"

_NO_PROGRESS_DIRECTIVE = (
    "当前 patch 没有改变任何根因签名。建议：① 重新读取报错的 at: 位置确认改的是否是"
    "正确文件；② 查询 RAG 获取该符号的确切迁移规则，而不是凭经验猜；"
    "③ 若连续多次仍无变化，本工具将在下一轮自动升级。"
)


def project_signature_set(view: "ProjectFilterView") -> frozenset[str]:
    """把 `ProjectFilterView.root_cause_errors` 投影成签名集合（方案文档 §2.1）。

    两层之间唯一的"数据转换"：只用 `local_signature`，绝不用 `noise_signature`
    （原因见 `verifier_filter_scheme.md` §6）；只投影 `root_cause_errors`，
    `symptoms`/`pending_pointers`/`dropped` 不计入——否则级联噪声会污染
    无进展/震荡检测。
    """
    return frozenset(e.local_signature for e in view.root_cause_errors)


def evaluate(
    state: ProjectVerifyState,
    request: VerifyGateRequest,
    cfg: RetryGateConfig,
) -> VerifyGateResult:
    """方案文档 §4.3 的完整判定逻辑。粒度契约（§2.2.4）：调用方必须保证 `request`
    携带的是 `verify_filter` 收敛循环之后的最终 `ProjectFilterView`，本函数不做
    任何"多轮内部子循环"的假设，一次调用只对应一个 Agent round。

    记账顺序（先记账，再判断）：
      0. round_index 防御性校验：`request.round_index != state.rounds_used + 1` 时
         只记录偏差（写进返回的 reason），不中断执行、不提升为 hard_stop。
      1. `state.signature_history.append(project_signature_set(request.project_view))`
      2. `state.rounds_used += 1`
      3. `state.cost_used_usd += request.round_cost_usd`（唯一写入点）
      4. 对 `request.patched_files` 中的每个文件 f：
         若 `state.per_file_last_signature_set.get(f)` 与本轮签名集合相同 → 计数 +1；
         否则（签名变了或第一次碰到）→ 计数重置为 1。随后更新
         `per_file_last_signature_set[f]` 为本轮签名集合。
      5. `infra_status != "OK"` → `infra_failure_streak += 1`，否则清零。

    `project_status` 合成规则：`"INFRA_FAILURE" if request.infra_status != "OK"
    else request.project_view.status`——即使未达到熔断阈值，单轮状态也要如实
    反映本轮的基础设施异常，不能沿用可能残缺/陈旧的 `project_view.status`。

    随后按 §4.2 的优先级顺序逐条判断，命中即通过内部 `_result(...)` 组装
    `VerifyGateResult` 并返回。
    """
    round_index_drift = request.round_index != state.rounds_used + 1

    sig_set = project_signature_set(request.project_view)
    state.signature_history.append(sig_set)
    state.rounds_used += 1
    state.cost_used_usd += request.round_cost_usd

    for path in request.patched_files:
        last_set = state.per_file_last_signature_set.get(path)
        if last_set == sig_set:
            state.per_file_patch_count[path] = state.per_file_patch_count.get(path, 0) + 1
        else:
            state.per_file_patch_count[path] = 1
        state.per_file_last_signature_set[path] = sig_set

    if request.infra_status != "OK":
        state.infra_failure_streak += 1
    else:
        state.infra_failure_streak = 0

    project_status: ProjectStatusWithInfra = (
        "INFRA_FAILURE" if request.infra_status != "OK" else request.project_view.status
    )

    if state.infra_failure_streak >= cfg.infra_failure_streak_limit:
        state.circuit_state = "OPEN"
        return _result(
            "CIRCUIT_OPEN",
            state=state,
            request=request,
            cfg=cfg,
            hard_stop=True,
            project_status=project_status,
            reason=(
                f"连续 {state.infra_failure_streak} 次基础设施失败（超时/崩溃），"
                "判定工作区不可用"
            ),
            round_index_drift=round_index_drift,
        )

    if state.rounds_used >= cfg.rounds_limit or state.cost_used_usd >= cfg.cost_limit_usd:
        return _result(
            "BUDGET_EXCEEDED",
            state=state,
            request=request,
            cfg=cfg,
            hard_stop=True,
            project_status=project_status,
            reason=(
                f"已用 {state.rounds_used}/{cfg.rounds_limit} 轮，"
                f"${state.cost_used_usd:.2f}/${cfg.cost_limit_usd:.2f}"
            ),
            round_index_drift=round_index_drift,
        )

    # 震荡检测固定识别最近 3 轮 A→B→A。oscillation_window 不是可调窗口：
    # 把它改成 5 也不会识别 A→B→C→A 的 4 轮周期（见 config.py 语义限制）。
    history = state.signature_history
    if len(history) >= 3 and history[-1] == history[-3] and history[-1] != history[-2]:
        preview = sorted(history[-1])[:3]
        return _result(
            "OSCILLATION_ESCALATE",
            state=state,
            request=request,
            cfg=cfg,
            hard_stop=True,
            project_status=project_status,
            reason=f"签名集合在最近 3 轮出现 A→B→A 震荡：{preview}...",
            round_index_drift=round_index_drift,
        )

    window = cfg.no_progress_window
    if len(history) >= window and all(sig == history[-1] for sig in history[-window:]):
        return _result(
            "NO_PROGRESS_WARN",
            state=state,
            request=request,
            cfg=cfg,
            hard_stop=False,
            project_status=project_status,
            reason=f"连续 {window} 轮签名集合未变",
            round_index_drift=round_index_drift,
            directive=_NO_PROGRESS_DIRECTIVE,
        )

    stuck_files = [
        path
        for path, count in state.per_file_patch_count.items()
        if count >= cfg.file_stuck_threshold
    ]
    if stuck_files:
        return _result(
            "FILE_STUCK_WARN",
            state=state,
            request=request,
            cfg=cfg,
            hard_stop=False,
            project_status=project_status,
            reason=f"文件 {stuck_files} 被反复 patch 但相关错误签名未变",
            round_index_drift=round_index_drift,
            directive=(
                f"{stuck_files} 已被修改 {cfg.file_stuck_threshold} 次以上仍未解决对应错误，"
                "建议改用不同的排查手段（读取该文件的 scene 依赖树 / 检索该符号的迁移规则），"
                "而不是继续用同一种改法重试。"
            ),
        )

    return _result(
        "CONTINUE",
        state=state,
        request=request,
        cfg=cfg,
        hard_stop=False,
        project_status=project_status,
        reason="有进展或首轮",
        round_index_drift=round_index_drift,
    )


def _result(
    decision: GateDecision,
    *,
    state: ProjectVerifyState,
    request: VerifyGateRequest,
    cfg: RetryGateConfig,
    hard_stop: bool,
    project_status: ProjectStatusWithInfra,
    reason: str,
    round_index_drift: bool = False,
    directive: str | None = None,
) -> VerifyGateResult:
    """把 `evaluate()` 算出的各项值组装成 `VerifyGateResult` 的内部辅助函数。

    职责：
    - 透传 `project_status`（合成结果，不是简单转发 `ProjectFilterView.status`）、
      以及 `request.project_view` 里的 `root_cause_errors`/`pending_pointers`/
      `caveats`/`untrusted_files`。
    - `round_index_drift=True` 时在 `reason` 末尾追加一句"调用方 round_index 与
      内部计数不一致"的提示，不改变 `decision`/`hard_stop`。
    - 计算 `GateDiff`：首轮（`len(state.signature_history) == 1`）没有"上一轮"可比，
      约定 `new_signatures = 本轮签名集合`，`resolved_signatures = ∅`，
      `persisted_signatures = ∅`；非首轮则对比 `state.signature_history` 最近两轮。
    - 组装 `BudgetSnapshot(rounds_used=state.rounds_used, rounds_limit=cfg.rounds_limit,
      cost_used_usd=state.cost_used_usd, cost_limit_usd=cfg.cost_limit_usd)`。
    """
    if hard_stop != (decision in _HARD_STOP):
        # 调用约定：硬停止决策与 hard_stop 必须同步，防止组装点各自为政。
        raise ValueError(f"hard_stop={hard_stop} 与 decision={decision} 不一致")

    if round_index_drift:
        reason = f"{reason}（{_ROUND_INDEX_DRIFT_HINT}）"

    history = state.signature_history
    current = history[-1] if history else frozenset()
    if len(history) <= 1:
        diff = GateDiff(
            new_signatures=current,
            resolved_signatures=frozenset(),
            persisted_signatures=frozenset(),
        )
    else:
        previous = history[-2]
        diff = GateDiff(
            new_signatures=current - previous,
            resolved_signatures=previous - current,
            persisted_signatures=previous & current,
        )

    view = request.project_view
    return VerifyGateResult(
        project_status=project_status,
        root_cause_errors=list(view.root_cause_errors),
        pointers=list(view.pending_pointers),
        caveats=list(view.caveats),
        untrusted_files=view.untrusted_files,
        gdscript_complete=view.gdscript_complete,
        shader_checked=view.shader_checked,
        probe_incomplete=len(view.pending_pointers) > 0,
        round_index=state.rounds_used,
        signature_set=current,
        diff=diff,
        decision=decision,
        hard_stop=hard_stop,
        reason=reason,
        directive=None if hard_stop else directive,
        remaining_budget=BudgetSnapshot(
            rounds_used=state.rounds_used,
            rounds_limit=cfg.rounds_limit,
            cost_used_usd=state.cost_used_usd,
            cost_limit_usd=cfg.cost_limit_usd,
        ),
    )
