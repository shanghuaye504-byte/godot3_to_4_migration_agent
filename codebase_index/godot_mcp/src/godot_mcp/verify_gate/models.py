"""数据模型 —— 方案文档 §2.2 与 §3。风格与 `verify_filter/models.py` 保持一致
（`frozen=True`、`Literal` 枚举、字段带来源注释），因为这两份文档描述的是同一条
流水线的相邻两段，接口风格不统一会增加实现者的认知负担。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from godot_mcp.verify_filter.models import ClassifiedEvent, ProjectFilterView

GateDecision = Literal[
    "CONTINUE",              # 一切正常，或有进展，允许 Agent 按常规流程继续
    "NO_PROGRESS_WARN",       # 连续 N 轮签名集合不变，软提示，仍允许继续，但建议换策略
    "FILE_STUCK_WARN",        # 同一文件反复被 patch 但签名不动，软提示
    "OSCILLATION_ESCALATE",   # A→B→A 震荡，硬停止，不再允许同策略重试
    "BUDGET_EXCEEDED",        # 轮次/成本预算耗尽，硬停止
    "CIRCUIT_OPEN",           # 基础设施连续失败（超时/崩溃）达到阈值，硬停止，工作区判定为不可用
]

ProjectStatusWithInfra = Literal["CLEAN", "HAS_ERRORS", "INFRA_FAILURE"]
"""比 `verify_filter.models.ProjectStatus` 多一个 `INFRA_FAILURE`——由 `algorithm.py`
的合成规则叠加（`INFRA_FAILURE if request.infra_status != "OK" else project_view.status`），
不是 `ProjectFilterView.status` 本身携带的值。"""


@dataclass(frozen=True)
class VerifyGateRequest:
    """一次 verify 工具调用，Gate 层看到的输入（方案文档 §2.2.1）。"""

    workspace_id: str                    # 用于定位历史状态，通常是仓库/任务的唯一 ID
    session_id: str                      # 一次迁移任务的会话 ID（跨 patch 轮次不变）
    round_index: int                     # 本次是第几轮（由调用方递增维护；algorithm.py 会做防御性校验，不中断执行）
    command: Literal["V1", "V2", "V3", "MERGED"]
    project_view: "ProjectFilterView"    # 来自 merge_command_results 的产出，只读；必须是收敛之后的最终结果（§2.2.4）
    patched_files: frozenset[str]        # 本轮 patch 触碰过的文件路径（用于"单文件反复卡住"检测）
    infra_status: Literal["OK", "TIMEOUT", "CRASH"] = "OK"  # 外壳报告的进程级状态，非 CLEAN/HAS_ERRORS
    round_cost_usd: float = 0.0          # 本轮（上一次 verify 调用结束到这一次之间）累计的 LLM 花费；唯一的成本输入通道


@dataclass(frozen=True)
class GateDiff:
    """本轮相对上一轮的签名集合差异，供 LLM 参考，也供人工审计（方案文档 §2.2.2）。

    首轮（`len(signature_history) == 1`）没有"上一轮"可比：约定
    `new_signatures = 本轮签名集合`，`resolved_signatures = ∅`，`persisted_signatures = ∅`。
    """

    new_signatures: frozenset[str]        # 本轮新出现、上一轮没有的根因
    resolved_signatures: frozenset[str]    # 上一轮有、本轮消失的根因（可能是真修好，也可能是被新错误挡住没跑到）
    persisted_signatures: frozenset[str]   # 两轮都有，完全没变的根因


@dataclass(frozen=True)
class BudgetSnapshot:
    rounds_used: int
    rounds_limit: int
    cost_used_usd: float
    cost_limit_usd: float


@dataclass(frozen=True)
class VerifyGateResult:
    """verify 工具调用最终返回给 Agent 循环的完整结果（方案文档 §2.2.2）。"""

    # --- 直接透传自 ProjectFilterView，Gate 不改写 ---
    project_status: ProjectStatusWithInfra   # 合成字段：INFRA_FAILURE 优先于 project_view.status，见 algorithm.py
    root_cause_errors: list["ClassifiedEvent"]
    pointers: list["ClassifiedEvent"]         # 对应 ProjectFilterView.pending_pointers
    caveats: list[str]
    untrusted_files: frozenset[str]

    gdscript_complete: bool                  # 透传 ProjectFilterView.gdscript_complete
    shader_checked: bool                     # 透传 ProjectFilterView.shader_checked
    probe_incomplete: bool                   # True ⇔ pending_pointers 非空；不触发硬停止

    # --- Gate 新增的判定结果 ---
    round_index: int
    signature_set: frozenset[str]
    diff: GateDiff
    decision: GateDecision
    hard_stop: bool                          # True ⇔ decision ∈ {OSCILLATION_ESCALATE, BUDGET_EXCEEDED, CIRCUIT_OPEN}
    reason: str                              # 人类/LLM 可读的一句话解释；round_index_drift 时会在末尾追加提示
    directive: str | None                    # 仅软提示时给出；硬停止时为 None
    remaining_budget: BudgetSnapshot


@dataclass
class ProjectVerifyState:
    """Gate 判定所需的跨轮次状态（方案文档 §3）。不能存在函数局部变量里，必须持久化。

    存储位置：单 worker/单会话场景用进程内内存字典；多 worker 场景换成 Redis
    （key 设计见 `state_store.py` 与方案文档 §3"存在哪里"），判定算法本身
    （`algorithm.py`）不关心状态具体存在哪里，只依赖"能读到、能写回去"这个接口。
    """

    workspace_id: str
    session_id: str
    signature_history: list[frozenset[str]]                  # 按轮次顺序，每轮的 root_cause 签名集合
    per_file_patch_count: dict[str, int]                       # 文件路径 -> 被 patch 的次数（签名不变才累加，签名变了重置为 1）
    per_file_last_signature_set: dict[str, frozenset[str]]     # 文件路径 -> 上次涉及该文件时的签名集合
    infra_failure_streak: int                                  # 连续 INFRA_FAILURE 次数
    rounds_used: int
    cost_used_usd: float                                       # 唯一写入点：algorithm.evaluate() 里的 += request.round_cost_usd
    circuit_state: Literal["CLOSED", "OPEN"] = "CLOSED"
    previous_view: ProjectFilterView | None = None  # 上一轮 collect 的项目视图；evaluate() 不读
    source_snapshot: dict[str, str] = field(default_factory=dict)  # relpath → 文本；evaluate() 不读
