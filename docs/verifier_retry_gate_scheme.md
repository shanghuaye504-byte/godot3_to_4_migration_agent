# Verifier 重试判定器（Retry Gate）设计方案

> **文档性质**：与 [`verifier_filter_scheme.md`](verifier_filter_scheme.md) 同级、互补。前者回答"怎么把 Godot 的输出变成可信的结构化错误"，本文回答"拿到这些结构化错误之后，谁来决定继续重试 / 换策略 / 熔断 / 升级人工，以及这个决定怎么传给 LLM"。
>
> **依赖关系**：本文档的全部输入，都是 `verifier_filter_scheme.md` §4 定义的 `FilterResult` 和 §7.10 定义的 `merge_command_results` 输出的 `ProjectFilterView`。不重复定义这些结构，只在需要处引用。
>
> **成熟度**：架构结论（分层边界、谁做判定）有明确的工业界依据，判定算法的具体阈值（N 轮无进展、震荡窗口大小）目前是从项目一期探针实验的结论 + 通用 Agent 工程实践推导出来的，**尚未做过专门的消融实验**，标记为"待验证"的地方在正文中会明确指出。

---

## 0. 背景：为什么这一块要单独拎出来

`verifier_filter_scheme.md` 在 §1 一开始就划了一条线：**过滤器是纯函数，不碰进程、不碰状态、不做决策，只负责"这一份文本该怎么理解"**。这条线划得非常对，但也意味着一个必然的后果：**"这一轮该不该继续重试""连续几轮同一批错误算不算无进展""什么时候该拒绝再重试、直接升级"——这些问题，过滤器天生回答不了，因为它连"上一轮长什么样"都不知道**。

这不是过滤器的疏漏，是职责分离的正确结果。但正因为如此，"重试怎么判定"这件事就悬空了——它既不在过滤器里，也没有被写进任何一份文档，只在最初的项目背景（CLAUDE.md）里提了一句"死循环检测、熔断、Redis 计数器"，没有具体到"输入输出是什么、代码放在哪一层、由谁做决定"。这份文档就是把这块悬空的逻辑落地。

在动手设计之前，必须先回答你提出的那个最关键的架构问题——**这个判定逻辑到底应该长在哪里**。这个问题不厘清，后面的 schema 设计无从谈起。

---

## 1. 核心问题：熔断/降级/升级的判定，到底该由谁做

### 1.1 先回答结论

**不是工具内部用"吐出特殊字符、指望被外层字符串嗅探拦截"的方式实现，也不是交给 LLM 自己判断。是一个独立于"过滤器"和"LLM"之外的、确定性的、有状态的中间层——姑且称为「Verify Gate」——它包裹在工具调用的边界内，对 LLM 表现为"就是那个 verify 工具的一部分"，但代码实现上是一个完全独立于噪声过滤器的有状态模块。**

用一句话概括三层关系：

```text
Godot 子进程（有副作用，慢）
   ↓ 原始 stdout/stderr
噪声过滤器（纯函数，无状态，逐次调用互不影响）——verifier_filter_scheme.md 的全部内容
   ↓ FilterResult / ProjectFilterView（结构化、可信、但只描述"这一次"）
Verify Gate（有状态，确定性代码，非 LLM）——本文档的全部内容
   ↓ VerifyGateResult（在 FilterResult 基础上，多了"这一轮相对历史处于什么阶段"的判断）
Agent 循环 / LLM（只在 Gate 允许的范围内做决策；Gate 判定的硬停止，LLM 无法绕过）
```

### 1.2 为什么不能让 LLM 自己判断"要不要熔断"

这不是"我们不信任 LLM 的智力"，是一个在 Agent 工程里反复被验证过的失效模式：**让模型自己评估"我是不是在原地打转""我是不是该放弃了"，模型系统性地过度乐观**。原因不复杂——每一轮它看到的都是"这次我改的这个点，道理上应该是对的"，它没有能力在单轮视角里看到跨轮次的宏观模式（比如"我在 A→B→A 之间震荡了 5 次"），除非有人把这个跨轮次的统计结果**明确喂给它**。早期 AutoGPT / BabyAGI 一类系统吃过这个亏：终止条件交给模型自己判断"任务完成了吗"，结果模型要么提前宣称完成（实际没完成），要么在死循环里自己都不知道要停（因为每一步看起来都"有进展"）。

工业界后来的共识（LangGraph 的 conditional edge、生产 Agent 框架里的 max-turn/budget 硬顶、包括 Cursor/Claude Code 这类工具自身的轮次与成本上限）都指向同一个原则：

> **凡是"控制流"层面的决策（继续/停止/升级/降级），必须由确定性的宿主代码（harness）掌控；模型只能在宿主允许的空间内做"内容"层面的决策（改哪一行、用什么方案）。**

模型可以，也应该，被**告知**"你已经震荡了 3 轮，请换个思路"，但不能被**赋予**"决定还要不要继续震荡下去"的权力——这是两回事。前者是把 Gate 的判断结果当成上下文喂给它（内容层面，模型仍然自主选择怎么应对），后者是把控制流的开关也交给它（模型可能会说"再试一次应该能成"，然后无限重试下去）。

### 1.3 为什么不用"工具吐出特殊字符，靠字符串嗅探拦截"

这是你自己提出的猜想，值得专门解释为什么不这么做。这个方案的问题不在"能不能工作"（技术上可以，字符串匹配总能凑合用），而在于它把一个**结构化的、需要被可靠识别的控制信号**，降级成了一个**脆弱的、隐式的文本约定**：

1. **可靠性问题**：LLM 生成的文本会被这条流水线的下一环解析。如果控制信号是"某个特殊字符串",一旦这个字符串意外出现在正常的错误消息、文件路径、或者 LLM 自己复述工具输出的文本里，会造成误触发或者信号丢失。结构化字段（一个 JSON 里的 `Literal["CONTINUE","ESCALATE",...]` 枚举字段）不存在"意外匹配"的问题，因为它是被程序按 key 读取的，不是被当成自由文本扫描的。
2. **可测试性问题**：字符串嗅探的正确性依赖于"这个特殊字符串在所有路径上都被完整保留、没有被截断或转义"，这种正确性很难写单元测试覆盖所有情况。结构化字段是一个 dataclass/schema，可以直接断言字段值，和 `verifier_filter_scheme.md` 里 `FilterResult` 的测试方式完全一致。
3. **语义澄清问题**：现代工具调用（function calling / MCP）协议本身就是结构化的——工具的返回值是 JSON，不是一段要靠正则去猜的自由文本。把控制信号做成返回 JSON 里的一个字段，是在使用协议本来就提供的能力；用特殊字符做带外信令（out-of-band signaling），是在协议已经支持结构化返回的情况下，反而退化回了字符串协议时代的做法。

所以正确做法是：**Verify Gate 的判定结果，就是 verify 这个工具调用返回值 schema 里的一个显式字段**，不需要任何字符串魔法。下一节给出具体 schema。

### 1.4 "Gate 在工具内部"到底是什么意思——避免另一个误解

这里要避免另一个容易产生的误解：说"Gate 在工具内部实现"，**不是说它和噪声过滤器是同一段代码**，而是说：**从 LLM 的视角看，它调用了一个叫 `run_verify`（或类似名字）的工具，这个工具的返回值里，既有"这次 Godot 输出解析出了什么错误"（过滤器的产出），也有"这一轮在整个重试历史里处于什么状态"（Gate 的产出）**。LLM 不需要，也不应该，额外调用一个"查一下我是不是要被熔断了"的工具——如果这么设计，会重新引入"模型可能忘记调用检查工具"这个脆弱点。**Gate 的计算必须是宿主代码在每次 verify 工具返回前无条件执行的，不依赖 LLM 主动请求。**

打个比方：这类似于 HTTP 请求里的 rate limit——服务端不会指望客户端"主动去问一下我还有没有配额"，而是每次请求都在响应头里带上 `X-RateLimit-Remaining`，配额用尽时直接返回 429，不管客户端愿不愿意。Verify Gate 扮演的就是这个角色：它不是一个要被主动查询的旁路服务，是每次 verify 调用的响应里都必然携带的一部分。

---

## 2. 三层的输入输出 Schema

### 2.1 第一层→第二层：噪声过滤器的输入输出（复述，不重复定义）

这一层完整定义在 `verifier_filter_scheme.md`，这里只列出 Gate 层需要消费的字段，作为衔接：

```text
filter_verify_output(raw_stdout, raw_stderr, *, command, autoload_keys, sentinel_res_paths)
    -> FilterResult(status, root_cause_errors, pointers, symptoms, dropped, caveats, untrusted_files)

merge_command_results(v1, v2_by_target, v3=None)
    -> ProjectFilterView（项目级视图；聚合后的 root_cause / pointers 未消化情况 / shader_not_checked 等 caveats）
```

Gate 层**只读**这两个函数的输出，不改写它们、不重新解析 Godot 文本。Gate 拿到 `ProjectFilterView` 之后要做的第一件事，是把 `root_cause_errors` 投影成一个签名集合：

```python
def project_signature_set(view: ProjectFilterView) -> frozenset[str]:
    return frozenset(e.local_signature for e in view.root_cause_errors)
```

这一步是两层之间唯一的"数据转换"，其余全部读取，不做二次判断（比如 Gate 不会去重新判断某条错误是不是假阳性——那是过滤器已经做完的事）。

### 2.2 第二层→第三层：Verify Gate 的完整 I/O Schema

#### 2.2.1 输入

```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class VerifyGateRequest:
    """一次 verify 工具调用，Gate 层看到的输入。"""
    workspace_id: str                    # 用于定位历史状态，通常是仓库/任务的唯一 ID
    session_id: str                      # 一次迁移任务的会话 ID（跨 patch 轮次不变）
    round_index: int                     # 本次是第几轮（由调用方递增维护，Gate 也会自行校验单调性）
    command: Literal["V1", "V2", "V3", "MERGED"]
    project_view: "ProjectFilterView"    # 来自 merge_command_results 的产出，只读
    patched_files: frozenset[str]        # 本轮 patch 触碰过的文件路径（用于"单文件反复卡住"检测）
    infra_status: Literal["OK", "TIMEOUT", "CRASH"] = "OK"  # 外壳报告的进程级状态，非 CLEAN/HAS_ERRORS
```

`infra_status` 单独存在的原因：超时/崩溃属于 `INFRA_FAILURE`，`verifier_filter_scheme.md` §4 已经明确这不属于 `FilterResult` 的职责范围，但 Gate 需要知道这件事——连续基础设施失败本身就是一种要熔断的信号（工作区可能已经损坏），这是和"错误签名不收敛"完全不同的另一种熔断触发源。

#### 2.2.2 输出

```python
GateDecision = Literal[
    "CONTINUE",             # 一切正常，或有进展，允许 Agent 按常规流程继续
    "NO_PROGRESS_WARN",      # 检测到连续 N 轮签名集合不变，软提示，仍允许继续，但建议换策略
    "FILE_STUCK_WARN",       # 检测到同一文件反复被 patch 但签名不动，软提示
    "OSCILLATION_ESCALATE",  # 检测到 A→B→A 震荡，硬停止，不再允许同策略重试
    "BUDGET_EXCEEDED",       # 轮次/成本预算耗尽，硬停止
    "CIRCUIT_OPEN",          # 基础设施连续失败（超时/崩溃）达到阈值，硬停止，工作区判定为不可用
]

@dataclass(frozen=True)
class GateDiff:
    """本轮相对上一轮的签名集合差异，供 LLM 参考，也供人工审计。"""
    new_signatures: frozenset[str]        # 本轮新出现、上一轮没有的根因
    resolved_signatures: frozenset[str]   # 上一轮有、本轮消失的根因（可能是真修好，也可能是被新错误挡住没跑到）
    persisted_signatures: frozenset[str]  # 两轮都有，完全没变的根因

@dataclass(frozen=True)
class VerifyGateResult:
    """verify 工具调用最终返回给 Agent 循环的完整结果。"""
    # --- 直接透传自 ProjectFilterView，Gate 不改写 ---
    project_status: Literal["CLEAN", "HAS_ERRORS", "INFRA_FAILURE"]
    root_cause_errors: list["ClassifiedEvent"]
    pointers: list["ClassifiedEvent"]
    caveats: list[str]
    untrusted_files: frozenset[str]

    # --- Gate 新增的判定结果 ---
    round_index: int
    signature_set: frozenset[str]
    diff: GateDiff
    decision: GateDecision
    hard_stop: bool                       # True ⇔ decision ∈ {OSCILLATION_ESCALATE, BUDGET_EXCEEDED, CIRCUIT_OPEN}
    reason: str                           # 人类/LLM 可读的一句话解释，如 "连续 3 轮签名集合未变：{a1b2..., c3d4...}"
    directive: str | None                 # 仅软提示时给出，具体建议见 §4.4；硬停止时为 None（不建议，是终止）
    remaining_budget: "BudgetSnapshot"

@dataclass(frozen=True)
class BudgetSnapshot:
    rounds_used: int
    rounds_limit: int
    cost_used_usd: float
    cost_limit_usd: float
```

这份 schema 刻意和 `verifier_filter_scheme.md` 保持同样的写法风格（`frozen=True`、`Literal` 枚举、字段带注释说明来源），原因是**这两份文档描述的是同一条流水线的相邻两段，接口风格不统一会增加实现者的认知负担**。

#### 2.2.3 谁来"运行"这个 Gate——一段编排伪代码

```python
def run_verify_tool(workspace_id: str, session_id: str, ...) -> VerifyGateResult:
    """这是 LLM 实际调用到的工具函数。对 LLM 而言，这是一个黑盒工具调用。"""
    # 1. 起 Godot 子进程，拿到原始 stdout/stderr（外壳职责，参照 verifier_filter_scheme.md §12）
    raw = run_godot_subprocess(...)

    # 2. 纯函数过滤（verifier_filter_scheme.md 的全部内容）
    filter_result = filter_verify_output(raw.stdout, raw.stderr, ...)
    project_view = merge_command_results(v1=..., v2_by_target=..., v3=...)

    # 3. Gate 判定（本文档的全部内容；有状态，读写 ProjectVerifyState）
    gate_request = VerifyGateRequest(workspace_id=workspace_id, session_id=session_id,
                                       round_index=..., project_view=project_view, ...)
    gate_result = verify_gate.evaluate(gate_request)   # 见 §4 的判定算法

    # 4. 硬停止：宿主代码在这里直接短路，不把"继续权"交给 LLM
    if gate_result.hard_stop:
        escalate_to_human_or_supervisor(workspace_id, gate_result)
        # 注意：这里仍然把 gate_result 返回给 LLM 所在的这一轮对话，
        # 但 Agent 循环的外层控制代码看到 hard_stop=True 后，
        # 不会再把"是否继续"这个选择权交给 LLM——循环由宿主强制结束。

    return gate_result
```

这段伪代码要点：**Gate 的判定发生在"工具函数返回给 LLM 之前"，是工具实现的一部分（对 LLM 表现为一次工具调用），但判定逻辑本身完全不依赖 LLM，也不依赖噪声过滤器——它是第三个独立的、有状态的代码模块**。这也回答了你的原始问题："重试计数是在 tool 的外面和 LLM 之前的一个模块实现"——准确地说，它在"工具调用的返回路径上"，物理上可以理解成"tool 外面、LLM 前面的一层包装"，但对外呈现为工具调用的一部分，不是一个需要 LLM 额外感知或调用的独立工具。

---

## 3. 状态存储：`ProjectVerifyState`

Gate 之所以需要"状态"，是因为它要回答的问题天生是跨轮次的（"和上一轮比怎么样""过去 3 轮怎么样"）。这个状态不能存在某次函数调用的局部变量里，必须持久化。

```python
@dataclass
class ProjectVerifyState:
    workspace_id: str
    session_id: str
    signature_history: list[frozenset[str]]           # 按轮次顺序，每轮的 root_cause 签名集合
    per_file_patch_count: dict[str, int]               # 文件路径 -> 被 patch 的次数
    per_file_last_signature_set: dict[str, frozenset[str]]  # 文件路径 -> 上次涉及该文件时的相关签名
    infra_failure_streak: int                          # 连续 INFRA_FAILURE 次数
    rounds_used: int
    cost_used_usd: float
    circuit_state: Literal["CLOSED", "OPEN"] = "CLOSED"
```

### 存在哪里

- **单 worker、单会话场景**（当前阶段够用）：进程内内存字典，`{(workspace_id, session_id): ProjectVerifyState}`，会话结束即释放。
- **多 worker、需要跨进程共享场景**（CLAUDE.md 里提到的分布式阶段）：Redis，key 设计为 `verify_state:{workspace_id}:{session_id}`，`signature_history` 用 Redis List 或直接整体序列化成 JSON 存 String（历史轮次不会太长，几十轮封顶，没必要拆分成 Redis 原生结构）。`circuit_state` 单独用一个带 TTL 的 key（`circuit:{workspace_id}`），方便熔断状态在没有活跃会话时也能被其它 worker 看到（工作区级熔断需要跨会话生效，防止同一个坏仓库被不同 worker 反复尝试）。

**这里刻意不在本文档里把 Redis 的具体读写代码定死**，因为这属于"外壳/基础设施选型"，和 `verifier_filter_scheme.md` 把"进程管理"排除在过滤器之外是同一个道理——Gate 的判定算法（§4）不应该依赖状态具体存在哪里，只依赖"能读到 `ProjectVerifyState`，能写回去"这个接口。

---

## 4. 判定算法

### 4.1 锁定的阈值配置

和 `verifier_filter_scheme.md` §2 一样的风格，把这些做成显式配置，不要散落在代码里的魔法数字：

```yaml
retry_gate:
  no_progress_window: 3        # 连续 N 轮签名集合完全不变 → NO_PROGRESS_WARN
  oscillation_window: 3        # A→B→A 检测的最小窗口
  file_stuck_threshold: 3      # 同一文件被 patch 的次数超过这个值、且相关签名不变 → FILE_STUCK_WARN
  infra_failure_streak_limit: 3   # 连续基础设施失败次数 → CIRCUIT_OPEN
  rounds_limit: 40             # 单会话最大轮次（硬顶）
  cost_limit_usd: 5.0          # 单会话最大花费（硬顶，具体数值按模型定价调整）
```

> **待验证标记**：`no_progress_window=3`、`oscillation_window=3`、`file_stuck_threshold=3` 这三个数字目前没有专门的消融实验支撑，是从通用 Agent 工程经验（"3 次不行大概率不会自己好"）里取的经验值。建议在反向变异集（`verifier_filter_scheme.md` 之外、项目原始规划里提到的"评测数据 B"）上跑一遍，统计"真正卡住需要几轮才能确认"和"多少轮内本来会自己收敛"的分布，再回填这里的数值，而不是继续沿用经验值。

### 4.2 判定顺序（优先级从高到低，一旦命中即返回，不再往下判断）

```text
1. infra_status != OK 且连续达到 infra_failure_streak_limit  → CIRCUIT_OPEN（硬停止）
2. rounds_used >= rounds_limit 或 cost_used_usd >= cost_limit_usd → BUDGET_EXCEEDED（硬停止）
3. 检测到 A→B→A 震荡（oscillation_window 内）                → OSCILLATION_ESCALATE（硬停止）
4. 连续 no_progress_window 轮签名集合完全相同                  → NO_PROGRESS_WARN（软提示）
5. 存在文件的 patch 次数 >= file_stuck_threshold 且相关签名未变 → FILE_STUCK_WARN（软提示）
6. 否则                                                        → CONTINUE
```

顺序本身有讲究：**硬停止条件必须排在软提示之前判断**，因为一旦命中硬停止，后面的软提示已经没有意义（Agent 循环都要结束了，不需要再告诉它"建议换个思路"）。基础设施熔断（第 1 条）排最前，是因为如果 Godot 进程本身都跑不起来，后面所有基于"签名集合"的判断都建立在不可靠的数据上，没有讨论的必要。

### 4.3 具体判定函数

```python
def evaluate(state: ProjectVerifyState, request: VerifyGateRequest, cfg: RetryGateConfig) -> VerifyGateResult:
    # --- 更新状态（先记账，再判断） ---
    sig_set = project_signature_set(request.project_view)
    state.signature_history.append(sig_set)
    state.rounds_used += 1
    for f in request.patched_files:
        state.per_file_patch_count[f] = state.per_file_patch_count.get(f, 0) + 1
        state.per_file_last_signature_set[f] = sig_set
    if request.infra_status != "OK":
        state.infra_failure_streak += 1
    else:
        state.infra_failure_streak = 0

    # --- 1. 基础设施熔断 ---
    if state.infra_failure_streak >= cfg.infra_failure_streak_limit:
        state.circuit_state = "OPEN"
        return _result("CIRCUIT_OPEN", hard_stop=True,
                        reason=f"连续 {state.infra_failure_streak} 次基础设施失败（超时/崩溃），判定工作区不可用")

    # --- 2. 预算耗尽 ---
    if state.rounds_used >= cfg.rounds_limit or state.cost_used_usd >= cfg.cost_limit_usd:
        return _result("BUDGET_EXCEEDED", hard_stop=True,
                        reason=f"已用 {state.rounds_used}/{cfg.rounds_limit} 轮，"
                               f"${state.cost_used_usd:.2f}/${cfg.cost_limit_usd:.2f}")

    # --- 3. 震荡检测 ---
    h = state.signature_history
    if len(h) >= cfg.oscillation_window and h[-1] == h[-3] and h[-1] != h[-2]:
        return _result("OSCILLATION_ESCALATE", hard_stop=True,
                        reason=f"签名集合在最近 3 轮出现 A→B→A 震荡：{sorted(h[-1])[:3]}...")

    # --- 4. 无进展 ---
    if len(h) >= cfg.no_progress_window and all(s == h[-1] for s in h[-cfg.no_progress_window:]):
        return _result("NO_PROGRESS_WARN", hard_stop=False,
                        reason=f"连续 {cfg.no_progress_window} 轮签名集合未变",
                        directive="当前 patch 没有改变任何根因签名。建议：① 重新读取报错的 at: 位置确认改的是否是"
                                    "正确文件；② 查询 RAG 获取该符号的确切迁移规则，而不是凭经验猜；"
                                    "③ 若连续多次仍无变化，本工具将在下一轮自动升级。")

    # --- 5. 单文件卡住 ---
    stuck_files = [f for f, n in state.per_file_patch_count.items() if n >= cfg.file_stuck_threshold]
    if stuck_files:
        return _result("FILE_STUCK_WARN", hard_stop=False,
                        reason=f"文件 {stuck_files} 被反复 patch 但相关错误签名未变",
                        directive=f"{stuck_files} 已被修改 {cfg.file_stuck_threshold} 次以上仍未解决对应错误，"
                                    "建议改用不同的排查手段（读取该文件的 scene 依赖树 / 检索该符号的迁移规则），"
                                    "而不是继续用同一种改法重试。")

    # --- 6. 正常 ---
    return _result("CONTINUE", hard_stop=False, reason="有进展或首轮")
```

（`_result(...)` 是把上面这些值组装成 `VerifyGateResult` 的辅助函数，附带计算 `GateDiff`，此处从略。）

### 4.4 软提示 `directive` 字段为什么要写成一段具体建议，而不是只给一个状态码

这是从 §1.2 那条"模型可以被告知，不能被赋权"原则里推出的实践细节：如果只给 LLM 一个 `NO_PROGRESS_WARN` 状态码，模型大概率的反应是"哦知道了，我再试一次"——因为它没有被告知"再试一次"具体应该有什么不同。`directive` 字段的作用是**把 Gate 观察到的宏观模式，翻译成一条具体的、可执行的策略调整建议**，缩小模型"知道有问题"和"知道该怎么应对"之间的差距。这条建议本身不需要很智能，甚至可以是模板化的固定文案（如上面例子），关键是它要指向一个和"重复上一轮做法"不同的具体动作。

---

## 5. 硬停止之后，Agent 循环具体怎么"被结束"

这一节回答一个容易被忽略的实现细节：`hard_stop=True` 不是"建议 Agent 停下来"，而是"Agent 循环的外层代码强制结束本轮会话"，两者的区别必须在代码层面体现出来：

```python
def agent_loop(session_id: str, workspace_id: str, max_llm_turns: int):
    for turn in range(max_llm_turns):
        llm_action = call_llm(context)
        if llm_action.tool_name == "run_verify":
            gate_result = run_verify_tool(workspace_id, session_id, ...)
            context.append(observation(gate_result))   # 无论软硬，都如实喂给 LLM

            if gate_result.hard_stop:
                # 关键：这里不再调用 LLM 去"决定"要不要继续。
                # 循环在宿主代码层面直接结束，硬停止的原因和数据被写进最终报告。
                write_final_report(workspace_id, gate_result, status="ESCALATED")
                return  # ← LLM 完全没有机会在这个 session 里再发一轮
        ...
    write_final_report(workspace_id, status="TURN_LIMIT_EXCEEDED")
```

这里有个细节值得强调：**即使 `hard_stop=True`，Gate 的结果仍然要如实写进 LLM 能看到的上下文里**（`context.append(observation(gate_result))`），不是悄悄把 LLM 踢出循环。这么做是为了让整个会话的记录是自洽的、可审计的——如果后续人工介入去看这个 session 的对话记录，能看到"模型看到了这个熔断信息，但循环在这里被宿主强制结束了"，而不是一个没头没尾的中断。这也是"模型可以被告知，但不能决定"的具体体现：**它被告知了，但它的下一步输出（哪怕它想说"再给我一次机会"）根本不会被执行**，因为 `return` 已经跳出了循环，不会再有下一轮 `call_llm`。

---

## 6. 与 `verifier_filter_scheme.md` 现有章节的关系

| 既有章节 | 关系 |
| --- | --- |
| §1 过滤器在整条 verifier 里的位置 | 那张流程图里"下游：Agent reward / 重试计数 / 熔断 / Judge"这一格，就是本文档展开的内容 |
| §2 `retry:` 配置块 | `count_symptoms/count_filtered_fp/count_only` 定义的是"哪些事件参与 Gate 的签名集合计算"，是本文档 §2.1 `project_signature_set` 函数的前提，本文档不重复定义、直接复用 |
| §6 两级 signature | `local_signature` 是本文档整个判定算法的唯一身份依据，本文档不重新发明签名机制 |
| §9 各命令下过滤器的预期行为 | "项目级完成"的判断（根因空 + pointer 消化 + shader 已查）是 `project_status` 字段的来源，Gate 不重新定义"完成"，只是在此基础上叠加"重试历史"这一维度 |
| §12 与外壳的分界 | 本文档的 Verify Gate 本身就是"外壳"的一部分，且是外壳里少数需要写详细算法的部分（对照 §12 表格里其它行大多是"确保 xxx 环境条件"，Gate 是真正有业务逻辑的一块） |

---

## 7. 建议的文件布局

```text
<pkg>/verify_gate/
  __init__.py        # run_verify_tool（组合过滤器 + Gate，对 LLM/MCP 暴露的入口）
  models.py           # VerifyGateRequest / VerifyGateResult / GateDiff / BudgetSnapshot / ProjectVerifyState
  config.py           # RetryGateConfig，对应 §4.1 的 YAML
  algorithm.py         # evaluate()，对应 §4.3
  state_store.py       # ProjectVerifyState 的读写接口；先给内存实现，留好 Redis 实现的接口
tests/
  test_algorithm_no_progress.py
  test_algorithm_oscillation.py
  test_algorithm_file_stuck.py
  test_algorithm_circuit_breaker.py
  test_algorithm_budget.py
  test_state_store_memory.py
```

`verify_gate/` 和 `verify_filter_scheme.md` §13 规划的 `verify_filter/` 是兄弟目录，两者不互相 import 内部实现，`verify_gate` 只依赖 `verify_filter` 导出的 `FilterResult` / `ProjectFilterView` 类型，不依赖其内部规则模块。

---

## 8. 测试矩阵

| ID | 场景 | 断言 |
| --- | --- | --- |
| G-CONT | 首轮，任意错误集合 | `decision=CONTINUE`，`hard_stop=False` |
| G-PROGRESS | 连续 3 轮签名集合递减且不同 | `decision=CONTINUE`（有进展，不触发无进展） |
| G-NOPROG | 连续 3 轮签名集合完全相同 | `decision=NO_PROGRESS_WARN`，`hard_stop=False`，`directive` 非空 |
| G-OSC | 签名集合出现 S0→S1→S0 | `decision=OSCILLATION_ESCALATE`，`hard_stop=True` |
| G-FILESTUCK | 同一文件被 patch 3 次，其涉及签名不变 | `decision=FILE_STUCK_WARN` |
| G-INFRA | 连续 3 次 `infra_status != OK` | `decision=CIRCUIT_OPEN`，`hard_stop=True` |
| G-BUDGET | `rounds_used == rounds_limit` | `decision=BUDGET_EXCEEDED`，`hard_stop=True` |
| G-PRIORITY | 同时满足"无进展"与"预算耗尽" | 只返回 `BUDGET_EXCEEDED`（验证 §4.2 的优先级顺序） |
| G-DIFF | 上一轮 {A,B}，本轮 {B,C} | `diff.new={C}`，`diff.resolved={A}`，`diff.persisted={B}` |
| G-SYMPTOM-EXCLUDED | 本轮唯一变化是新增了一条 symptom（非 root_cause） | 签名集合不受影响，不触发任何状态变化（验证 §2.1 只投影 `root_cause_errors`） |

---

## 9. 明确不要做的事

1. 不要让 LLM 通过自然语言自己判断"是否该停止重试"——判断权必须在 Gate 的确定性代码里，LLM 只接收结果。
2. 不要用特殊字符串/魔法 token 做工具到宿主之间的控制信号；一律用结构化字段（`GateDecision` 枚举）。
3. 不要把 Gate 的判定逻辑和噪声过滤器的规则写进同一个模块；两者的输入输出性质不同（无状态 vs 有状态），混在一起会让两边都难测试。
4. 不要在 Gate 判定里重新解析 Godot 原始文本；Gate 只消费 `ProjectFilterView`，不知道、也不需要知道 stderr 长什么样。
5. 不要用 `noise_signature` 做 Gate 的判定依据；必须是 `local_signature`（原因见 `verifier_filter_scheme.md` §6）。
6. 不要把 `symptoms` / `pointers` / `dropped` 算进签名集合；只用 `root_cause_errors`，否则级联噪声会污染无进展/震荡检测（呼应 `verifier_filter_scheme.md` §0 第 3 点）。
7. 硬停止（`hard_stop=True`）之后不要再把"继续"的选择权交还给 LLM；宿主必须在代码层面强制结束循环，不能只是"建议"结束。
8. 不要把 `rounds_limit` / `cost_limit_usd` 这类硬顶做成可以被 LLM 参数化修改的值；这些是宿主级别的安全阈值，不应该出现在 LLM 能影响的任何输入路径上。
9. 不要在没有真实数据支撑的情况下，把 §4.1 的经验阈值当成"已验证"写进核心配置——目前它们仍标记为待验证。

---

## 10. 完成定义

1. §8 全部测试用例通过。
2. `VerifyGateResult` 的字段和 `verifier_filter_scheme.md` 的 `FilterResult`/`ProjectFilterView` 字段没有重复定义或语义冲突（透传字段一致、新增字段互不覆盖）。
3. 存在至少一个集成测试：模拟连续 3 轮完全相同的 `ProjectFilterView`，断言最终从 `run_verify_tool` 返回的 `hard_stop` 序列是 `[False, False, True]`（第 3 轮才因无进展窗口满足触发……注意：`NO_PROGRESS_WARN` 本身 `hard_stop=False`，这里用于验证软提示按预期轮次出现，不与硬停止混淆）。
4. 硬停止分支有对应测试验证"宿主循环在返回 `hard_stop=True` 后不再调用 LLM"（可以用 mock 断言 `call_llm` 的调用次数）。
5. 代码路径上不存在任何"解析 LLM 自由文本来判断是否熔断"的逻辑。
