"""数据模型 —— 方案文档 §4 与 §7.10.1。

分两层，刻意不合并（方案文档 §4 的注解）：

- `RawEvent`：只负责"把一段文本正确切成结构化字段"，不做任何是非判断。
- `ClassifiedEvent`：在 `RawEvent` 基础上加"这条事件属于哪一类、该怎么处理"的判断结果。

`ClassifiedEvent` 是 `frozen=True`：规则改 `role`/`drop_reason` 必须用
`dataclasses.replace(event, role=..., drop_reason=...)`，禁止就地赋值——这样每条规则的
输出都是一份新对象，出错时只需要在规则之间打印快照就能定位是哪一步改错的（方案文档 §7
"后一条规则看到的是前一条 replace 过的事件"）。

`res_path` 与 `target_res_path` 必须是两个独立字段，不能合并（方案文档 §4"陷阱"一节）：
`res_path` 是"引用方"（谁在报错），`target_res_path` 是"pointer 指向的目标"（该对谁跑
V2）。字段用错的后果是 Agent 永远对不坏的文件重复跑 V2，真正坏的文件永远查不到。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Kind = Literal[
    "parse_error",
    "compile_error",
    "shader_error",
    "resource_error",
    "engine_error",
    "warning",
    "unknown",
]

Role = Literal[
    "root_cause",       # 进 reward、进重试计数
    "pointer",           # Could not preload/resolve；路由 V2 用，不进重试
    "symptom",           # 级联 / 包装行；给 LLM 参考，不进 retry
    "false_positive",    # 已确认噪声，删除
    "infra_noise",       # 调试器未挂上等
    "cluster_member",    # 被压缩进另一条 root_cause
    "protected",         # 禁止过滤（真冲突、真缺失）
]

DropReason = Literal[
    "autoload_identifier_fp",
    "sentinel_artifact",
    "depended_scripts_compile",
    "failed_to_load_wrapper",
    "uid_duplicate_satellite",
    "debugger_plugin_detached",
    "warning_not_in_reward",
    "duplicate_local_signature",
]

CommandKind = Literal["V1", "V2", "V3", "V5"]
ProjectStatus = Literal["CLEAN", "HAS_ERRORS"]


@dataclass(frozen=True)
class RawEvent:
    """解析后、过滤前的一条原子事件（方案文档 §4）。

    每一条 SCRIPT ERROR / SHADER ERROR / ERROR / WARNING（含其 `at:` continuation
    行）算一条，由 `parse.py` 按 §5.1 的行语法切出。
    """

    prefix: Literal["SCRIPT ERROR", "SHADER ERROR", "ERROR", "WARNING"]
    message: str                    # 冒号后的原文，不含 prefix
    at_function: str | None         # 如 GDScript::reload / load / shader_set_code
    at_location: str | None         # 括号内原文，如 res://uses_autoload.gd:4
    res_path: str | None            # 只从 at: 抽出的项目脚本路径（引用方 / 报错所在文件）
    target_res_path: str | None     # 只从 message 抽出的目标路径（pointer 的 V2 对象）
    line_in_project: int | None     # 仅 SCRIPT ERROR 指向项目脚本时；ERROR 的引擎行号不进此字段
    engine_location: str | None     # 如 modules/gdscript/gdscript_resource_format.cpp:46
    source_stream: Literal["stderr", "stdout"]
    raw_block: str                  # 含 continuation 的原文，供 LLM


@dataclass(frozen=True)
class ClassifiedEvent(RawEvent):
    """`RawEvent` + 分类/签名/角色判断结果（方案文档 §4/§5.2/§6）。

    改字段只能用 `dataclasses.replace(event, ...)`，不允许就地赋值。
    """

    kind: Kind
    symbol: str | None               # Identifier / Class "X" / pointer 时等于 target_res_path
    local_signature: str             # sha1 hex；项目内身份，用于去重/重试计数/震荡检测
    role: Role = "root_cause"
    drop_reason: DropReason | None = None
    cluster_id: str | None = None
    compile_truncated: bool = False


@dataclass
class FilterResult:
    """单次命令、一份 stderr 的过滤结果（方案文档 §4）。不含 `INFRA_FAILURE`。

    单次 vs 项目级禁止混用：本结果的 `status=CLEAN` 只表示"这一份日志没有可进 reward
    的根因"，不代表项目已经迁移完成——`pointers` 非空时仍可能是 `CLEAN`（样例 F）。
    项目级完成判断交给 `merge_command_results` 产出的 `ProjectFilterView`。
    """

    status: ProjectStatus                     # HAS_ERRORS ⇔ root_cause_errors 非空
    root_cause_errors: list[ClassifiedEvent]
    pointers: list[ClassifiedEvent]            # 非空不改变本字段 status，见方案文档 §9
    symptoms: list[ClassifiedEvent]
    dropped: list[ClassifiedEvent]
    caveats: list[str]                         # 如 compile_truncated:res://foo.gd
    untrusted_files: frozenset[str]


@dataclass(frozen=True)
class ProjectFilterView:
    """`merge_command_results` 的返回值：跨多次命令、项目级的聚合视图（方案文档 §7.10.1）。

    与单次 `FilterResult` 的区别：这里的 `root_cause_errors` 已经把"pointer 对应的
    V2 根因"并入，不会出现"同一个根因既挂在 pointer 上、又在 V2 结果里"的重复计数。

    `gdscript_complete`/`shader_checked` 是派生字段，由 `merge_command_results` 组装
    时算出来（见 `merge.py` 的公式），调用方不需要另算一遍。
    """

    status: ProjectStatus                       # 项目级；不含 INFRA_FAILURE，那是外壳/Gate 叠加的信息
    root_cause_errors: list[ClassifiedEvent]     # 已消化 pointer 之后的根因全集（跨 V1/V2/V3 去重）
    pending_pointers: list[ClassifiedEvent]       # 仍未被对应 V2 消化的 pointer
    symptoms: list[ClassifiedEvent]
    dropped: list[ClassifiedEvent]
    caveats: list[str]                            # 含 shader_not_checked / uid_undetectable_without_duplicate 等
    untrusted_files: frozenset[str]
    gdscript_complete: bool                        # (root_cause_errors 为空) and (pending_pointers 为空)
    shader_checked: bool                           # v3 is not None
