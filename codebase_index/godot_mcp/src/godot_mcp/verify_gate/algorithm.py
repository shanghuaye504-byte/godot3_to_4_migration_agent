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

`evaluate()` 的人话说明（入参/记账/六条决策）写在函数自己的 docstring 里。
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
    """看完「这一轮校验结果」之后，决定 Agent 该继续修、该换策略，还是该停手。

    本函数不启动 Godot，也不解析日志。前面的外壳已经跑完 V1/V2/V3、滤过错，
    把一张项目视图放进 ``request.project_view``。这里只做两件事：
    **先把本轮记进会话账本（会改 ``state``）**，再按优先级给出一个决策。

    三个参数：
    - ``state``：这个仓库 + 这次迁移会话的记忆（已经用了几轮、花了多少钱、
      前几轮的根因指纹、哪个文件被反复改过）。必须由调用方在返回后 ``save``。
    - ``request``：这一轮的客观结果。核心是 ``project_view``（根因/未消化的
      pointer/是否干净）和 ``infra_status``（进程是否超时或崩溃）。
      ``patched_files`` 是 Agent 本轮改过的文件；``round_cost_usd`` 是本轮花费。
    - ``cfg``：阈值（连续几次算无进展、预算上限等）。

    一次调用 = Agent 的一轮，不是外壳里面那几次 Godot 子循环。调用方必须传入
    已经 merge 完的最终视图，本函数不会再去下钻 pointer。

    先记账（改 ``state``），再判断——判断用的是记下之后的数字：
    1. 调用方给的 ``round_index`` 若不是「已用轮数 + 1」，只在返回的 ``reason``
       里提一句，不因此停手。
    2. 从本轮根因算出签名集合（每个根因一个稳定指纹，不含 pointer/症状），
       追加到 ``signature_history``。
    3. 轮次 +1，累加花费（会话成本只在这里加）。
    4. 对每个被 patch 的文件：若本轮根因签名和上次改它时一样，补丁次数 +1；
       签名变了或第一次碰到，次数重置为 1。用来抓「同一文件改了三遍还是那些错」。
    5. Godot 超时/崩溃 → 连续失败次数 +1；否则清零。

    项目状态：进程不健康就标 ``INFRA_FAILURE``（即使还没熔断）；否则沿用过滤器
    的 CLEAN / HAS_ERRORS。不能在超时时还显示「项目干净」。

    然后从上到下只命中第一条（硬停止必须先于软提示；进程都起不来时，
    后面的「签名没变」不可信）：

    1. 连续超时/崩溃达到上限 → ``CIRCUIT_OPEN``，硬停止，工作区当坏掉。
    2. 轮次或美元预算用尽 → ``BUDGET_EXCEEDED``，硬停止。
    3. 最近三轮根因集合呈 A→B→A → ``OSCILLATION_ESCALATE``，硬停止
       （改 A 冒出 B，改回去又变成 A，同策略再试没有意义）。
    4. 连续 N 轮根因集合完全一样 → ``NO_PROGRESS_WARN``，软提示，仍允许继续。
    5. 某文件被反复 patch 且相关签名没变 → ``FILE_STUCK_WARN``，软提示。
    6. 否则 → ``CONTINUE``（有进展，或这是第一轮还没有历史可比）。

    返回值把过滤器的根因/pointer/caveat 原样带上，并附上 ``decision``、
    ``hard_stop``、相对上一轮的签名 diff、剩余预算。软提示时还有 ``directive``
    （建议 Agent 换读文件/查规则的方式）；硬停止时 ``directive`` 为空。
    """
    # --- 记账：先写入本轮，下面的判断用的是更新后的 state ---
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

    # --- 判定：从上到下只取第一条命中 ---
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
