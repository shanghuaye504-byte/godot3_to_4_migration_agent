# Godot 4.7.1 Verifier 噪声过滤方案（开发指导）

> **文档性质**：按本文件即可实现过滤器代码。结论全部来自 `godot_test/probe_tests` 第一阶段探针（N01–N09、N15）在 Godot `4.7.1.stable.official.a13da4feb` 上的实测。
>
> **证据入口**：人写结论见 `godot_test/probe_tests/reports/README.md`；原始 stderr 在对应 `artifacts/<run-id>/`。本文只引用已确认的文案与决策，不抄实验步骤。
>
> **范围**：本文规定「如何把 Godot 的 stdout/stderr 变成 Agent 可用的 reward」。采集命令、进程组、超时、import 触发器属于 verifier **外壳**，只在它们会改变过滤正确性时写死；不在这里实现 runner。

---

## 0. 背景：为什么必须过滤

生产 verifier 的客观信号是：

```text
V1  哨兵项目级 --check-only（preload 全部 *.gd）
V2  单文件 --check-only
V3  --headless --path $P --editor --import --quit
```

这三路输出**不能原样当 reward**。探针已经确认：

1. **退出码不可信**（N08）：干净项目、真语法错误、纯假阳性的 `exit_code` 全是 `0`。`success = (rc == 0)` 会把坏仓库判成通过。
2. **假阳性会诱导 Agent 改正确代码**（N01 / N02）：`--check-only` 不加载 autoload / 已写入 `[autoload]` 的插件单例，稳定报 `Compile Error: Identifier not found: <单例名>`。符号在运行时真实存在。若不过滤，Agent 会去「声明」一个已经存在的单例，或把正确调用改坏。
3. **症状行会淹没根因**（N04）：多级 `preload` 不会把语法错误复制到每个文件，但会额外打出 `Failed to compile depended scripts`、哨兵自身的 compile error、以及 `Failed to load script ... Compilation failed` 包装行。这些行进重试计数器会误触发熔断。
4. **严重度通道是断的**（N05）：CLI 默认看不到 warning；打开 `gdscript/warnings/enable` 也看不到；唯一能看到 warning 的 `--debug` 会 signal 11 崩溃（N08）。因此 **warning 不进 reward、不进终止条件**。UID 重复时夹带的 WARNING 只能当聚类线索，不能当修复目标列表。
5. **盲区与假阴性**（N03 / N06 / N07）：冷缓存下 `class_name` 会报「找不到」；单独篡改 UID 完全静默；shader 错误 V1/V2 看不见、只有 V3/V5 看得见。这些**不能靠过滤行解决**，由外壳用「入队一次 WARM + 条件性 import」约束（§2.1），**不是每轮 verify 都跑 V3**。外壳若在 COLD 缓存上跑 V1/V2，过滤器会把冷缓存假阳性当成真缺失。

一句话：**Godot 4.7.1 的 check-only 是带噪声、会中途停编、覆盖不全的解析器输出。过滤器的职责是删掉已确认的假阳性与症状，保住真错误，并显式标出「这一文件的编译可能被截断、不能宣称干净」。**

---

## 1. 过滤器在整条 verifier 里的位置

V3 import 成本高。N03 的决策就是**条件性触发器**，不是每轮必跑。入队建立 WARM 与「本轮是否再 import」必须分开画：

```text
[外壳：超时 / killpg / workspace 锁 / 禁 --debug]
        │
        ▼
[入队一次]
   无 global_script_class_cache.cfg 或需 UID 规范化 → V3，标记 cache=WARM
   已有 WARM → 禁止无故 rm -rf .godot/
        │
        ▼
[每轮 patch 后：只看本轮 diff + 缓存态]
   触发表命中 → 本轮 V3
   已 WARM 且仅普通 .gd 函数体 → 跳过 V3
        │
        ▼
[采集（可重复）]
   V1 → merge 抽出 target_res_path → 对各 target V2
   → 若本轮刚消化过 pointer，再 V1 直到 pointer 集稳定或达上限
        │
        ▼
[本模块]  parse → signature → filter（单次）
[聚合]    merge_command_results（§7.10）
        │
        ▼
[收尾门] 项目级 GDScript 未完成? → 不跑收尾，回 Agent
         根因空 且 pointer 已消化 且 本轮没跑过 V3 → 再 V3 一次
         V3 若打出 SHADER / UID 根因 → 本轮 HAS_ERRORS，回 Agent
         只有跑过收尾且仍无根因 → 才算本轮验证结束
        │
        ▼
[下游：Agent reward / 重试计数 / 熔断 / Judge]
```

触发表、伪代码与「什么叫已验证 shader」见 **§2.1**。过滤器不启动 V3。

过滤器是**纯函数**，无 Godot 子进程、无 IO（读取 `project.godot` 的 `[autoload]` 段由调用方完成，结果作为参数传入）。

```text
filter_verify_output(
    raw_stdout: str,
    raw_stderr: str,
    *,
    command: Literal["V1", "V2", "V3", "V5"],
    autoload_keys: frozenset[str],
    sentinel_res_paths: frozenset[str],   # 默认 frozenset({"res://__probe_sentinel.gd"})
) -> FilterResult

merge_command_results(
    v1: FilterResult,
    v2_by_target: dict[str, FilterResult],
    v3: FilterResult | None = None,
) -> ProjectFilterView
```

`shader_not_checked` **不要**由 `filter_verify_output` 凭空添加（它不知道本轮有没有跑过 V3）。由外壳在聚合时写入：若 `v3 is None`，则 `ProjectFilterView.caveats` 含 `shader_not_checked`。

**禁止**在过滤器内部根据 V5 是否启动成功来决定删不删某一行（N01/N02 明确否决）。V5 只给外壳做交叉验证，不进本模块。

---

## 2. 已锁定、实现时不得改口的配置

对标 `reports/README.md` §5。下列取值已经由实验填死；实现过滤器时把它们当成常量，不要再「先跑一遍再决定」。

```yaml
godot:
  version: "4.7.1.stable.official.a13da4feb"
  build_hash: "a13da4feb"

verifier:
  project_check: V1
  success_source: parsed_errors          # 禁止 exit_code == 0
  report_status: [CLEAN, HAS_ERRORS, INFRA_FAILURE]  # 项目级；过滤器只出前两态
  require_warm_cache: true               # 不变量：global_script_class_cache.cfg 存在；≠ 每轮 import
  allow_debug: false                     # N08：signal 11
  enable_warnings: false                 # N05：CLI 收集不到
  shader_channel: V3_on_trigger_or_final_gate  # N07：V1/V2 看不见；V3 只由触发表或收尾门启动
  use_runtime_cross_check: true          # 外壳使用；过滤器不用

noise_filters:
  autoload: project_godot_keys           # N01：WARM 也消不掉，必须白名单
  addon_singleton: reuse_autoload        # N02：启用后 key 已写入 [autoload]
  cascade_symptoms: drop_from_reward     # N04
  uid_duplicate_cluster: collapse_to_one # N06
  debugger_plugin_noise: drop            # N06 伴随噪声
  class_name_cold_cache: do_not_filter   # N03：靠 §2.1 缓存不变量 + 条件触发，禁止按文案过滤
  single_uid_tamper: undetectable        # N06：过滤器看不见；入队 wipe+rebuild，不要每轮为 UID 付 V3

retry:
  count_symptoms: false
  count_filtered_fp: false
  count_only: root_cause_errors

import_policy:                           # 外壳懒启动表，见 §2.1；过滤器不执行
  class_name_added: true                 # N03 T4–T6：diff 命中才 V3
  class_name_renamed: true               # 未测（ISSUE 缺口），保守触发
  gd_file_added: true                    # N03 T4 与 class_name 绑在一起测过；拆开未测，保守触发
  shader_or_shader_tres_changed: true    # N07：否则本轮看不见 shader
  uid_duplicate_repair: true             # 删冲突 .uid 之后必须再 V3 验证
  ordinary_gd_body_changed: false        # 未测；默认不触发
  scene_ext_resource_changed: false      # N06：引用变更不报错
  uid_changed: false                     # N06：单条篡改不报错也不能靠再 import 自愈
  autoload_script_changed: false         # N01：import 消不掉 FP
```

`require_warm_cache: true` **不是**「每次 V1/V2 前先跑一遍 V3」。它禁止外壳在 **没有** `.godot/global_script_class_cache.cfg` 时采集（仅有空 `.godot/` 目录仍算 COLD）。那种日志里的 `Parse Error: Identifier "ProbeFoo" not declared in the current scope` 与 autoload FP **不是同一模板**，过滤器不得按文案去补救。已 WARM 的工作区直接 V1/V2；本轮要不要再 import 只看 §2.1 触发表。

---

## 2.1 外壳：import 懒启动（N03 最贵结论）

过滤器不实现本节。实现 runner 的人必须按这里写，禁止把 §1 理解成「verify = import + check」。

N03 原文分叉：T4 报错 → 做**条件性**触发器（diff 里 grep `class_name`、检测新文件），代价是命中时每轮 +N 秒；T4 若干净则 import 只需一次。实测 T4 报错，所以触发器要做，但默认路径仍是跳过 V3。N15：先 V1 静态纠错，再 V3 查 shader/UID——那是**阶段门**，不是每轮。

### 2.1.1 三个概念，禁止合并

| 概念 | 何时 V3 | 不做什么 |
| --- | --- | --- |
| **缓存不变量** | 没有 `.godot/global_script_class_cache.cfg`，或入队需要 UID 规范化 | 禁止无故删 `.godot/`；不要只看目录是否存在 |
| **本轮触发器** | 这一轮 diff 命中下表「触发」行 | 普通函数体、autoload 脚本、改 `ext_resource` 路径、普通 `.tres` 改色都不触发 |
| **收尾门** | **项目级** GDScript 根因为空 **且** pointer 已全部被 V2 消化，且本轮还没跑过 V3 | 项目级未完成时不要跑收尾；收尾打出新根因必须回 Agent |

### 2.1.2 触发表（只看本轮 diff）

检测方式全部是对 **unified diff + 文件增删列表** 的离线检查，不要起 Godot 来「问问要不要 import」。

| 条件 | 是否 V3 | 怎么检测 | 依据 |
| --- | --- | --- | --- |
| 新增 / 删除 / 改名 `class_name` 行 | 是 | diff 行匹配 `^[+-]class_name\s`（不要子串 grep，注释/字符串会误触发）；改名 = 同一 hunk 里 `-class_name A` 与 `+class_name B` | N03 T4–T6；改名缺口未测，保守触发 |
| 新增 `.gd` 文件 | 是 | 路径出现在 diff 的 `new file` 侧 | N03 `gd_file_added` |
| 变更 shader | 是 | 路径以 `.gdshader` / `.shader` 结尾，**或** `.tres` hunk 里出现 `.gdshader` / `shader_type`。普通 `.tres` 改色 **不** 触发 | N07 |
| 本轮正在修 UID 重复（删除冲突 `.uid`） | 是 | diff 删除了 `.uid`，或上一份项目视图含 UID duplicate 根因且本轮动了那些路径 | N06 |
| 普通 `.gd` 函数体（不碰 `class_name`、不是新文件） | 否 | 默认 | 未测；ISSUE-import-trigger-coverage-gaps |
| `.tscn` 的 `ext_resource` 改路径 | 否 | — | N06 |
| 单条 `.uid` 文本被改（非重复簇修复） | 否 | — | N06；只在入队 wipe |
| 只改引用 autoload 的脚本 | 否 | — | N01 |
| 缓存已 WARM，diff 为空 | 否 | — | 直接 V1/V2 |

`ordinary_gd_body_changed` 若后续补实验推翻，只改本表，不改过滤器。

### 2.1.3 判定伪代码

```text
function cache_is_warm(workspace) -> bool:
    return workspace.has_file(".godot/global_script_class_cache.cfg")

function should_run_v3(workspace, diff, project_view, *, phase) -> bool:
    if phase == intake:
        return (not cache_is_warm(workspace)) or intake_needs_uid_wipe
    if phase == final_gate:
        return project_view.gdscript_complete and not v3_ran_this_iteration
        # gdscript_complete ⇔ 根因空 且 无未消化 pointer
    if not cache_is_warm(workspace):
        return true
    if diff.line_matches(r"^[+-]class_name\s"): return true
    if diff.added_gd_file():                    return true
    if diff.path_endswith((".gdshader", ".shader")): return true
    if diff.hunk_contains(".tres") and diff.hunk_contains((".gdshader", "shader_type")):
        return true
    if is_uid_duplicate_repair(diff, project_view): return true
    return false
```

每轮顺序：

```text
if should_run_v3(..., phase=iteration):
    V3
loop:                                          # V1 必须可重复（N04 哨兵提前结束）
    V1 → filter → 对每个 pointer.target_res_path 跑 V2
    merge_command_results(...)
    若本轮刚消化过 pointer 且（新 V1 又给出新 target 或集合仍在变）
        → 再 V1，直到 pointer 集稳定或达到上限（建议 8）
if project_view.gdscript_complete and not v3_ran_this_iteration:
    V3                                         # 收尾门
    并入 v3 的 FilterResult
    若 v3.root_cause_errors 非空 → 本轮项目级 HAS_ERRORS，回 Agent
    不要把「跑过收尾门」当成迁移完成
```

`shader_not_checked` 只在聚合时、`v3 is None` 时由外壳写入。

### 2.1.4 入队 UID 规范化（仍只一次）

N06：单独伪造 UID 在 V1/V2/V3 上全静默，再 import 也不会自愈。外壳入队时在**隔离 workspace** 里 `rm **/*.uid` 再 V3 **一次**，把 duplicate 暴露出来并重建 sidecar。禁止对用户原仓做 `git rm`。之后不要每轮为「说不定 UID 坏了」再付一次 import。

---

## 3. 实现顺序（按这个顺序写代码与测试）

每一步有独立单测、不依赖 Godot 二进制。样例必须从真实 artifacts 摘，禁止手写猜测的文案。推荐把样例放在实现包的 `tests/fixtures/godot_4_7_1/`，每份文件头注释 `artifact: <相对路径>`。

| 步 | 模块 | 完成标准 |
| -- | ---- | -------- |
| 1 | `models.py` | 下文 §4 的 dataclass 能 round-trip；`replace()` 能改 role |
| 2 | `parse.py` | §5 全部样例能解析；pointer 的 `target_res_path` ≠ `res_path`（样例 F） |
| 3 | `signature.py` | 同一错误改行号后 `local_signature` 不变；不同 `res://` 路径 `local` 不同、`noise` 相同 |
| 4 | `autoload.py` | 能从 `project.godot` 文本解析 `[autoload]` 的 **key** |
| 5 | `rules/*.py` | 按 §7.1–§7.8 顺序跑；禁止在规则里改 frozen 字段（用 replace） |
| 6 | `pipeline.py` | 组装 `FilterResult`；`status` 只看 `root_cause_errors` |
| 7 | `merge.py` | `merge_command_results`：V2 根因消化 pointer；未 V2 的 pointer 保持项目级未完成 |
| 8 | 回归包 | §10 的黄金样例全绿 |

不要先写「一个大 regex 扫全文」。必须先切行、再分类、再过滤。Godot 把一条逻辑错误打成 2–6 行，合并错了后面全错。

---

## 4. 数据模型

```python
from dataclasses import dataclass, replace
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
    "root_cause",          # 进 reward、进重试计数
    "pointer",             # Could not preload/resolve；路由 V2 用，不进重试
    "symptom",             # 级联 / 包装行；给 LLM 参考，不进 retry
    "false_positive",      # 已确认噪声，删除
    "infra_noise",         # 调试器未挂上等
    "cluster_member",      # 被压缩进另一条 root_cause
    "protected",           # 禁止过滤（真冲突、真缺失）
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

@dataclass(frozen=True)
class RawEvent:
    """解析后、过滤前的一条原子事件（SCRIPT ERROR / SHADER ERROR / ERROR / WARNING 各算一条）。"""
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
    kind: Kind
    symbol: str | None              # Identifier / Class "X" / pointer 时等于 target_res_path
    msg_template: str               # 路径、符号、数字占位符化之后
    local_signature: str            # sha1 hex
    noise_signature: str            # sha1 hex
    role: Role = "root_cause"
    drop_reason: DropReason | None = None
    cluster_id: str | None = None
    compile_truncated: bool = False

@dataclass
class FilterResult:
    """单次命令、一份 stderr 的过滤结果。不含 INFRA_FAILURE。"""
    status: Literal["CLEAN", "HAS_ERRORS"]  # HAS_ERRORS ⇔ root_cause_errors 非空
    root_cause_errors: list[ClassifiedEvent]
    pointers: list[ClassifiedEvent]         # 非空不改变本字段 status，见 §9 项目级规则
    symptoms: list[ClassifiedEvent]
    dropped: list[ClassifiedEvent]
    caveats: list[str]                      # 如 compile_truncated:res://foo.gd
    untrusted_files: frozenset[str]
```

`ClassifiedEvent` 是 frozen 的：规则改 `role` / `drop_reason` 必须 `replace(event, role=..., drop_reason=...)`，禁止 `event.role = ...`。

`INFRA_FAILURE` **不属于** `FilterResult`。timeout / signal / 进程崩溃由外壳写成项目级 `VerifyReport.status`。过滤器只出 `CLEAN` 或 `HAS_ERRORS`：`root_cause_errors` 为空则为 `CLEAN`（仍可能有 `pointers` / `caveats` / `untrusted_files`）。

**单次 vs 项目级（禁止混用）**：

- 单次 `FilterResult.status=CLEAN` 只表示「这份日志没有可进 reward 的根因」。样例 F（V2 `dep_1.gd`）就是 CLEAN + 一条 pointer。
- **项目级未完成** ⇔ 任一命令的根因非空 **或** 仍有 `target_res_path` 未被对应 V2 消化。禁止把单次 `passed = (status == CLEAN)` 用在项目级。
- `untrusted_files` 非空时，禁止宣称这些文件已证明没有别的编译问题；也不因此把单次 status 改成 HAS_ERRORS。

N04 pointer 实测（两个路径必须拆开，用错会永远 V2 引用方）：

```text
Could not preload resource script "res://root_bad.gd"   ← target_res_path，外壳只对它跑 V2
at: GDScript::reload (res://dep_1.gd:3)                 ← res_path，引用方
```

---

## 5. 解析器（`parse.py`）

### 5.1 行语法（4.7.1 实测，不要放宽到「任意 ERROR」）

Godot 一条事件 = **1 行前缀 + 1 行 `at:` continuation**。`at:` 行以空白开头。

```text
SCRIPT ERROR: <inner>
          at: <func> (<location>)
ERROR: <inner>
   at: <func> (<location>)
WARNING: <inner>
     at: <func> (<location>)
SHADER ERROR: <inner>
          at: (null) (:<line>)
```

正则（实现时用 `re.MULTILINE`，先按「前缀行」切块，再读下一块是否为 `at:`）：

```python
PREFIX = re.compile(
    r"^(?P<prefix>SCRIPT ERROR|SHADER ERROR|ERROR|WARNING): (?P<message>.*)$"
)
AT_SCRIPT = re.compile(
    r"^\s+at: (?P<func>\S+) \((?P<res>res://[^:)]+):(?P<line>\d+)\)$"
)
AT_ENGINE = re.compile(
    r"^\s+at: (?P<func>\S+) \((?P<eng>[^)]+\.(?:cpp|h|mm):\d+)\)$"
)
AT_SHADER = re.compile(
    r"^\s+at: \(null\) \(:?(?P<line>\d+)\)$"
)
AT_GENERIC = re.compile(
    r"^\s+at: (?P<func>\S+) \((?P<loc>[^)]*)\)$"
)
```

匹配优先级：`AT_SCRIPT` → `AT_ENGINE` → `AT_SHADER` → `AT_GENERIC`。

字段怎么填：

- `res_path`：优先 `AT_SCRIPT` 的 `res://`。若 `at:` 是引擎路径（包装行、UID Busy），则从 **message** 里抽 `res://`（`Failed to load script "res://X"` / `Failed loading resource: res://X` / Busy 的 Resource file）。不要把引擎 cpp 路径写进 `res_path`。
- `target_res_path`：仅 pointer 文案从 message 抽；其余事件为 `None`。外壳 V2 只用这个字段。

### 5.2 inner message 再分类

对 `SCRIPT ERROR` / `ERROR` 的 `message` 再抽 `kind` 与 `symbol`：

| 匹配（完整 `message`） | kind | symbol | 后续角色（默认，过滤前） |
| --- | --- | --- | --- |
| `Compile Error: Identifier not found: (?P<sym>\S+)` | compile_error | sym | 待 autoload 规则 |
| `Parse Error: Class "(?P<sym>[^"]+)" hides an autoload singleton.` | parse_error | sym | **protected** |
| `Parse Error: Identifier "(?P<sym>[^"]+)" not declared in the current scope.` | parse_error | sym | **protected**（真缺失或 N03 冷缓存；过滤器都不删） |
| `Parse Error: Could not preload resource script "(?P<path>res://[^"]+)"\.` | parse_error | path → **target_res_path** | **pointer** |
| `Parse Error: Could not resolve script "(?P<path>res://[^"]+)"\.` | parse_error | path → **target_res_path** | **pointer** |
| `Compile Error: Failed to compile depended scripts.` | compile_error | None | **symptom** 候选 |
| `Failed to load script "(?P<path>res://[^"]+)" with error "(?P<why>Parse error\|Compilation failed)"\.` | resource_error | path | **symptom** 候选 |
| `Failed loading resource: (?P<path>res://\S+)\.` | resource_error | path | UID 簇候选 |
| `Parse Error: Busy. \[Resource file (?P<path>res://[^:]+):(?P<line>\d+)\]` | resource_error | path | UID 簇候选 |
| `UID duplicate detected between (?P<a>res://\S+) and (?P<b>res://\S+)\.` | warning | None | 簇根 |
| `Plugin is not attached to debugger.` | engine_error | None | infra_noise |
| `Shader compilation failed.` | shader_error | None | 包装，挂到前一条 SHADER ERROR |
| `Invalid arguments for the built-in function: "..."`（SHADER ERROR 前缀） | shader_error | 函数名 | root_cause |
| 其余 `Parse Error: ...` | parse_error | None | root_cause |
| 其余 `Compile Error: ...` | compile_error | None | root_cause |

未匹配的 `ERROR:` 默认为 `engine_error` / `root_cause`，宁可不滤，不可默删。

### 5.3 必须能解析的黄金原文（从 artifacts 原样拷贝）

**A. autoload FP（N01 COLD V2）**

```text
SCRIPT ERROR: Compile Error: Identifier not found: Config
          at: GDScript::reload (res://uses_autoload.gd:4)
ERROR: Failed to load script "res://uses_autoload.gd" with error "Compilation failed".
   at: load (modules/gdscript/gdscript_resource_format.cpp:46)
```

**B. 真 autoload 冲突，禁止过滤（N01 AL-SHADOW）**

```text
SCRIPT ERROR: Parse Error: Class "Config" hides an autoload singleton.
          at: GDScript::reload (res://shadow_config.gd:1)
ERROR: Failed to load script "res://shadow_config.gd" with error "Parse error".
   at: load (modules/gdscript/gdscript_resource_format.cpp:46)
```

**C. V1 放大 + 哨兵症状（N01 V1 WARM）**

```text
SCRIPT ERROR: Compile Error: Identifier not found: Config
          at: GDScript::reload (res://main.gd:4)
SCRIPT ERROR: Compile Error: Identifier not found: Config
          at: GDScript::reload (res://uses_autoload.gd:4)
SCRIPT ERROR: Compile Error: Failed to compile depended scripts.
          at: GDScript::reload (res://__probe_sentinel.gd:0)
ERROR: Failed to load script "res://__probe_sentinel.gd" with error "Compilation failed".
   at: load (modules/gdscript/gdscript_resource_format.cpp:46)
```

**D. addon 单例，与 A 同规则（N02）**

```text
SCRIPT ERROR: Compile Error: Identifier not found: DummySingleton
          at: GDScript::reload (res://uses_addon.gd:4)
ERROR: Failed to load script "res://uses_addon.gd" with error "Compilation failed".
   at: load (modules/gdscript/gdscript_resource_format.cpp:46)
```

**E. 真语法错误（N08 / N04 分母）**

```text
SCRIPT ERROR: Parse Error: Expected parameter name.
          at: GDScript::reload (res://orphan_bad_parse.gd:3)
ERROR: Failed to load script "res://orphan_bad_parse.gd" with error "Parse error".
   at: load (modules/gdscript/gdscript_resource_format.cpp:46)
```

```text
SCRIPT ERROR: Parse Error: Unexpected "Indent" in class body.
          at: GDScript::reload (res://scene_bad.gd:4)
ERROR: Failed to load script "res://scene_bad.gd" with error "Parse error".
   at: load (modules/gdscript/gdscript_resource_format.cpp:46)
```

**F. 一级依赖 pointer（N04 dep_1）**

```text
SCRIPT ERROR: Parse Error: Could not preload resource script "res://root_bad.gd".
          at: GDScript::reload (res://dep_1.gd:3)
SCRIPT ERROR: Parse Error: Could not resolve script "res://root_bad.gd".
          at: GDScript::reload (res://dep_1.gd:3)
ERROR: Failed to load script "res://dep_1.gd" with error "Parse error".
   at: load (modules/gdscript/gdscript_resource_format.cpp:46)
```

**G. 二级依赖 + depended scripts（N04 leaf）**

```text
SCRIPT ERROR: Parse Error: Could not preload resource script "res://root_bad.gd".
          at: GDScript::reload (res://dep_1.gd:3)
SCRIPT ERROR: Parse Error: Could not resolve script "res://root_bad.gd".
          at: GDScript::reload (res://dep_1.gd:3)
SCRIPT ERROR: Compile Error: Failed to compile depended scripts.
          at: GDScript::reload (res://leaf.gd:0)
ERROR: Failed to load script "res://leaf.gd" with error "Compilation failed".
   at: load (modules/gdscript/gdscript_resource_format.cpp:46)
```

**H. 冷缓存 class_name（N03 T1）——禁止当 autoload FP 删**

```text
SCRIPT ERROR: Parse Error: Identifier "ProbeFoo" not declared in the current scope.
          at: GDScript::reload (res://uses_class.gd:4)
ERROR: Failed to load script "res://uses_class.gd" with error "Parse error".
   at: load (modules/gdscript/gdscript_resource_format.cpp:46)
```

**I. UID 重复簇（N06 V3）**

```text
WARNING: UID duplicate detected between res://sub.tscn and res://main.tscn.
     at: _process_file_system (editor/file_system/editor_file_system.cpp:1405)
ERROR: Parse Error: Busy. [Resource file res://sub.tscn:6]
   at: _parse_node_tag (scene/resources/resource_format_text.cpp:293)
ERROR: Failed loading resource: res://sub.tscn.
   at: _load (core/io/resource_loader.cpp:317)
ERROR: Parse Error: Busy. [Resource file res://main.tscn:7]
   at: _parse_node_tag (scene/resources/resource_format_text.cpp:293)
ERROR: Failed loading resource: res://main.tscn.
   at: _load (core/io/resource_loader.cpp:317)
ERROR: Plugin is not attached to debugger.
   at: is_active (editor/debugger/editor_debugger_plugin.cpp:102)
```

**J. shader（N07 V3）**

```text
SHADER ERROR: Invalid arguments for the built-in function: "vec4(float,float,float)".
          at: (null) (:4)
ERROR: Shader compilation failed.
   at: shader_set_code (servers/rendering/dummy/storage/material_storage.cpp:192)
```

V5 的 stdout 里会多出带 `E   4->` 的源码上下文（N07）。解析器对 stdout 只抽取 `SHADER ERROR` 同类块与 `E\s+\d+->` 行，挂到对应 shader 事件的 `raw_block`，**不单独再造一条 root_cause**。

### 5.4 明确不解析进事件的内容

- `Godot Engine v4.7.1...` 横幅
- 项目自己的 `print`（如 `CONFIG_ALIVE`、`NP_SHADER_MAIN_STARTED`）
- 空 stderr（CleanControl V1/V3 实测经常为空）：结果是零事件，不是解析失败

---

## 6. 两级 signature（`signature.py`）

规格来自 N09，横向确认「随项目而变的只有 `res://` 文件名」。

```text
normalized_message =
    把 message 里的 res://... 换成 <RES>
    把 Identifier not found: Foo / Identifier "Foo" / Class "Foo" 里的符号换成 <SYM>
    删除一切 :数字 形式的项目行号
    不删除引擎路径里的 cpp 行号（N09：ERROR 跟的是引擎源码，行号固定，可作症状同一性依据）

local_signature  = sha1(kind | res_path_or_empty | symbol_or_empty | normalized_message)
noise_signature  = sha1(kind | msg_template)

msg_template = normalized_message 再把 <RES>/<SYM> 之外残留的路径与数字全部换成占位符
```

比较集合时：

- 用 `local_signature` 做项目内去重、震荡检测、retry 计数。
- **不要**用 `noise_signature` 做过滤。它会把 `Identifier not found: Config` 和 `Identifier not found: SomeMissingClass` 折成同一模板。N09 原文陷阱：BG 减法只是实验期粗筛；生产过滤必须回到 `local_signature` + 白名单符号。
- `VerifyReport` 的 error 集合是按 `local_signature` 排序后的 set，不是 list。行号不得进入 signature（patch 会移动行号）。行号仍保留在 `line_in_project`，只传给 LLM。

引擎 `at:` 路径（`gdscript_resource_format.cpp:46`）**可以**进入 `msg_template` 的稳定部分，用来判断「多条 ERROR 包装是否同一症状」。

---

## 7. 过滤流水线（顺序固定，禁止重排）

后一条规则看到的是前一条 `replace` 过 `role` 的事件。顺序的理由写在每一步下面。R8 不在本流水线：它需要多份命令的结果，见 §7.9。

```text
parse
  → classify inner message（§5.2 默认 role）
  → 标记 protected（§7.1）
  → R1 哨兵人造边
  → R2 autoload / addon Identifier-not-found FP
  → R3 depended-scripts 症状
  → R4 Failed-to-load 包装行
  → R5 UID 重复簇压缩
  → R6 debugger plugin 噪声
  → R7 warning 降级（不进 reward）
  → R8 按 local_signature 去重
  → 组装 FilterResult
```

### 7.1 保护名单（先打标，后续规则碰到 `protected` 必须 skip）

满足任一即 `role = protected`，**永远不得改为 false_positive / symptom / drop**：

| 条件 | 证据 | 若误删的后果 |
| --- | --- | --- |
| `Parse Error: Class "…" hides an autoload singleton.` | N01 AL-SHADOW | 真命名冲突被当成 FP |
| `Parse Error: Identifier "…" not declared in the current scope.` | N02 补实验 + N03 | 真缺失被删；或把冷缓存问题伪装成「已过滤」 |
| 任意 `kind=parse_error` 且 **不是** §5.2 表中的 pointer 三种文案 | N04 分母、N08 真错 | 语法错误是 reward 本体 |
| `SHADER ERROR:` 前缀 | N07 | 唯一能看见的 shader 根因 |

「Compile Error: Identifier not found: X」**不在**保护名单。它是 R2 的输入。

### 7.2 R1 哨兵人造边

```text
若 res_path 以 __probe_ 为文件名前缀
   或 res_path ∈ sentinel_res_paths
则：
  - Compile Error: Failed to compile depended scripts → drop sentinel_artifact
  - Failed to load script "res://__probe_sentinel.gd" → drop sentinel_artifact
  - Parse Error: Could not preload/resolve 且 at 在哨兵上
        → role=pointer（不要 drop）
        → target_res_path = message 里的 res://X.gd（V2 只跑这个，不要跑哨兵）
```

依据：N01「哨兵 compile error 一定对应前面已经打出的其它脚本错误」；N04「V1 只点到哨兵直接 preload 的根，文案是 Could not preload/resolve，不是真实语法」。

### 7.3 R2 autoload / addon 假阳性（核心）

**白名单来源**：只解析 `project.godot` 的 `[autoload]` 段的 **key**。N02 确认插件 `add_autoload_singleton` 启用后会写入该段（`DummySingleton="*uid://..."`），不必扫 addon 源码。

```ini
[autoload]
Config="*res://config.gd"
DummySingleton="*uid://qmfp8cu17gl2"
```

key 是等号左侧，去掉空白。值里的 `*`、`res://`、`uid://` 忽略。

**只删这一类行**：

```text
prefix == SCRIPT ERROR
message 精确匹配  Compile Error: Identifier not found: {KEY}
KEY ∈ autoload_keys
且 role 不是 protected
```

然后：

1. 将该事件 `role=false_positive`，`drop_reason=autoload_identifier_fp`。
2. 把该事件的 `res_path` 加入 `untrusted_files`，caveat 写：
   `compile_truncated:{res_path}（#check-only 在 autoload FP 处停编译，同文件后续 Compile Error 可能从未打出）`。
3. **不要**因为本文件只剩这条 FP，就把文件或项目标成「已证明干净」。
4. **不要**用 V5 决定删不删。
5. **不要**删 `Parse Error: Identifier "X" not declared...`，即使 X 碰巧等于某个 autoload key。
6. **不要**删 `Identifier not found: X` 当 X 不在 `autoload_keys` 里——那是真缺失的编译错误。

N02 补实验的编译截断事实必须写成代码注释，紧挨这条规则：

- 同文件后面若是 **Parse Error**（未声明标识符、类型赋错、语法）：引擎仍会打出，R2 删 Config 行不会让它们消失。
- 同文件后面若是 **Compile Error**（对已声明 Node 调不存在的方法）：引擎常被 Config 挡住，日志里可能只剩 Identifier-not-found。过滤器删不掉「没出现的行」。这是 FN，用 `untrusted_files` 声明，不要假装没有。

### 7.4 R3 `Failed to compile depended scripts`

```text
message == "Compile Error: Failed to compile depended scripts."
→ role=symptom, drop_reason=depended_scripts_compile
```

N04：一级引用只有 preload/resolve，没有这条；二级及以上每层一条。它不描述根因，禁止进 retry。事件仍放进 `symptoms` 给 LLM（「这个文件依赖链断了」）。

若该行的 `res_path` 是哨兵，R1 已经 drop，本规则 skip。

### 7.5 R4 `Failed to load script` 包装

包装行的 `res_path` 取 message 里的脚本路径（与 `at:` 引擎路径无关）。

```text
message 匹配 Failed to load script "res://..." with error "Parse error|Compilation failed"
→ role=symptom, drop_reason=failed_to_load_wrapper
```

它几乎总是紧跟在一条 SCRIPT ERROR 之后，引擎位置固定为 `gdscript_resource_format.cpp:46`（N09 纵向稳定）。reward 只保留上面的 SCRIPT ERROR。

**若 SCRIPT ERROR 已被 R2 删掉（autoload FP），包装也删，禁止升级成根因。** 样例 A 滤掉 Config 之后恰好只剩包装；若升级，T-A 会失败，等于把 FP 送回 reward。

**升级例外（窄）**：只看**解析完成、过滤开始之前**的事件集。当且仅当该 `res_path` 在原始解析结果里**从未出现过任何 SCRIPT ERROR**（引擎只打了包装、没有正文）时，才把包装升为 `root_cause`。因 FP / 症状被删而变空的，不升级。4.7.1 探针未出现「只有包装」形态；用合成样例锁住例外，用 T-A 锁住「不得因 R2 升级」。

### 7.6 R5 UID 重复簇

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

N06：后面 ERROR 数量是严重度假阳性，实质是同一个问题；删掉两个场景的 UID 再 V3 即可。不要让 Agent 去修 `Busy`。

单独伪造 UID、没有 duplicate WARNING 时：探针确认 V1/V2/V3 **全静默**。过滤器无事可做。外壳入队必须在隔离 workspace `rm **/*.uid` 再 V3 **一次**（§2.1.4）；过滤器文档化这个盲区即可（caveat 不按文件生成，由外壳写 `uid_undetectable_without_duplicate`）。

### 7.7 R6 调试器插件噪声

```text
message == "Plugin is not attached to debugger."
→ role=infra_noise, drop_reason=debugger_plugin_detached
```

N06 在 UID 重复的 V3 日志末尾稳定出现。与脚本对错无关。

### 7.8 R7 warning 与终止条件

`prefix == WARNING` 的事件：

- 若已被 R5 提升为 UID 簇根，保留为 `root_cause`（这是唯一例外：文案是 WARNING，但 N06 确认它代表真实的、会让 import 失败的问题）。
- 其余 WARNING：`role` 保持信息性，**不进入** `root_cause_errors`，`drop_reason=warning_not_in_reward`。

N05：默认与注入 warning 开关后 CLI 都收集不到普通 GDScript warning；不要为实现「第二档信号」去开 `--debug`。

`status`（单次）:

```text
HAS_ERRORS  ⇔  len(root_cause_errors) > 0
CLEAN       ⇔  否则（pointers / caveats / untrusted 均可非空）
```

`symptoms`、`dropped`、`pointers`、WARNING 默认都不改变**单次** `status`。项目级是否完成见 §9。

### 7.9 去重（原 R9）

同一 `local_signature` 只留第一次出现的事件（stderr 顺序稳定，N09 确认 repeat 间顺序完全一致）。集合对外按 `local_signature` 字典序排序。单次过滤到此结束。

同一 `target_res_path` 上成对的 `Could not preload` 与 `Could not resolve` 合并为一条 pointer。

### 7.10 聚合函数 `merge_command_results`（原 R8，不在单次流水线里）

`filter_verify_output` 只吃一份 stdout/stderr，看不见「后来那次 V2」。V1 与多次 V2 的合并是**第二个纯函数**，由外壳在跑完一轮采集后调用：

```text
merge_command_results(v1: FilterResult, v2_by_target: dict[str, FilterResult]) -> ProjectFilterView
```

```text
S = {p.target_res_path for p in v1.pointers}  # 已扣哨兵 res_path
对 S 中每个 target 跑 V2（若尚未跑）
若 V2(target).root_cause_errors 非空
    → 丢弃指向该 target 的 pointer（根因已在 V2 里，避免计两次）
若 V2(target) 根因为空（只剩被滤掉的 FP）
    → 丢弃 pointer，把 target 并入 untrusted_files
若某 pointer 还没有对应 V2
    → 项目级未完成，即使各次 status 都是 CLEAN
```

单次 V2（样例 F）**必须仍输出 pointer**，过滤器不得假装已经 drill-down。

N04 / N08：V1 **报不全、也不报具体语法**。修完本轮 pointer 目标后必须再 V1（§2.1），因为哨兵 Parse Error 会提前结束，autoload FP 与更长 preload 链可能根本不在第一份 V1 日志里。

---

## 8. `[autoload]` 解析（`autoload.py`）

输入：`project.godot` 全文。不要用 Godot 去读。

规则：

1. 找到行首 `[autoload]`（允许前后空白）。
2. 读到下一个 `^[` 或 EOF。
3. 忽略空行与 `;` / `#` 开头的注释。
4. 匹配 `^(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*.+$`。
5. 只返回 key 的 frozenset。

N02 derived patch 实测值含 `uid://`，所以**不要**断言值必须是 `res://`。key 才是白名单。

插件未启用时 `[autoload]` 不存在 → 空集 → R2 不删任何 Identifier-not-found。这是正确行为。

---

## 9. 各命令下过滤器的预期行为（给外壳的契约）

| 命令 | 过滤器当主输出看什么 | 过滤器不负责的事 |
| --- | --- | --- |
| V1 | pointers（`target_res_path`）+ 可能出现的 autoload FP + 哨兵症状（删） | 不能当「项目所有脚本的完整错误列表」；单次 CLEAN 仍可能有 pointer |
| V2 | 该文件的 parse/compile 根因；autoload FP；包装行；若是依赖方则仍可能是 pointer | 看不到 shader、看不到 UID |
| V3 | shader 根因、UID 重复簇、import 期 ERROR | 不是 GDScript 语法的主通道；只由 §2.1 触发器或收尾门启动 |
| V5 | 可选：把 stdout 里 shader 上下文并入已有 SHADER ERROR | 启动成功 ≠ 脚本正确（N08 B9）；rc=0 无意义 |

**单次 `passed`（仅 MCP / 旧接口，且仅这一份日志）**：

```text
passed = (status == "CLEAN")   # 即 root_cause_errors 为空；pointer 非空时仍为 True
```

**项目级禁止用上面这行。** 项目级完成 ⇔ 所有根因为空 **且** 无未消化的 `target_res_path` **且** 已有一次 V3 覆盖 shader（否则带 `shader_not_checked`，不算对外宣称迁移完成）。`INFRA_FAILURE` 只由外壳在 timeout/signal 时写入项目级报告。

不要把 `untrusted_files` 折进单次 `passed=False`。`shader_not_checked` 由 `merge_command_results` / 外壳写入，不由单次 filter 猜。

---

## 10. 测试矩阵（实现时逐条写成 pytest）

每条：给定 `(stderr, stdout, autoload_keys, command)` → 断言 `root_cause` / `dropped.reason` / `untrusted_files` / `pointers`。

| ID | 输入 | autoload_keys | 断言 |
| --- | --- | --- | --- |
| T-A | 样例 A | `{Config}` | 0 条 root_cause；1 条 FP drop；`uses_autoload.gd` ∈ untrusted；包装行 dropped |
| T-A2 | 样例 A | `{}` | 1 条 root_cause（Identifier not found: Config），**不删** |
| T-B | 样例 B | `{Config}` | 1 条 root_cause（hides an autoload）；0 条 FP drop |
| T-C | 样例 C | `{Config}` | 0 条 root_cause；两条 FP；哨兵 depended + Failed to load 均 drop |
| T-D | 样例 D | `{DummySingleton}` | 与 T-A 同构 |
| T-E | 样例 E | 任意 | 1 条 parse root_cause；包装 symptom |
| T-F | 样例 F | 任意 | `status=CLEAN`；1 条 pointer，`target_res_path=res://root_bad.gd`，`res_path=res://dep_1.gd`；无 Unexpected Indent |
| T-G | 样例 G | 任意 | pointer 同 T-F（`target_res_path=res://root_bad.gd`）；depended scripts 为 symptom；leaf 包装 drop |
| T-H | 样例 H | `{ProbeFoo}` 或 `{}` | **都必须留下** Parse Error not declared；不得当 FP |
| T-I | 样例 I | 任意 | 恰好 1 条 UID duplicate root_cause；Busy/Failed loading 为 cluster；debugger 行 drop |
| T-J | 样例 J | 任意 | 1 条 SHADER ERROR root_cause；`Shader compilation failed` 为包装 symptom |
| T-LINE | 样例 E 把 `:3` 改成 `:99` | 任意 | `local_signature` 与原文相同 |
| T-SYM | A 与 D | 各自白名单 | `noise_signature` 相同，`local_signature` 因 symbol/path 不同 |
| T-MIX | 同一 stderr：Config FP + Unexpected Indent（不同文件） | `{Config}` | Indent 必须留下 |
| T-STOP | 文档化用例：仅 Config FP，无其它行 | `{Config}` | status=CLEAN 且 untrusted 非空 |

样例文件从下列 artifacts 拷贝（不要改空白）：

- A: `probe_tests/artifacts/20260822-164829/N01/np-autoload/s1/COLD/1/stderr.log`
- B: `.../N01/np-autoload/s7/WARM/1/stderr.log`
- C: `.../N01/np-autoload/s5/WARM/1/stderr.log`
- D: `.../20260822-225134/N02/np-addon/s2/WARM/1/stderr.log`
- E: `.../20260822-135953/N08/np-syntax/v2/WARM/1/stderr.log`
- F/G: `.../20260823-115551/N04/np-cascade/s4|s5/WARM/1/stderr.log`
- H: `.../20260822-144626/N03/np-globalclass/t1/COLD/1/stderr.log`
- I: `.../20260823-180913/N06/np-resource/s7/WARM/1/stderr.log`
- J: `.../20260823-182940/N07/np-shader/s2/COLD/1/stderr.log`

---

## 11. 明确不要做的事

1. 不要扫 `add_autoload_singleton(` 建白名单（N02：贵且不可靠，key 已在 `project.godot`）。
2. 不要用强制 WARM 替代 R2（N01：WARM 后 FP 仍在）。WARM 只解决冷启动的 class_name 假阳性，不要每轮 import 去「维持 WARM」。
3. 不要过滤 `Identifier "X" not declared in the current scope`。
4. 不要把 `Failed to compile depended scripts` 当根因修。
5. 不要把 UID 簇的 5 条 ERROR 当 5 个问题。
6. 不要把 `Plugin is not attached to debugger` 当插件坏了。
7. 不要采集 warning 当第二档 reward，不要为此启用 `--debug`。
8. 不要用 `noise_signature ∈ 背景集` 作为生产过滤条件。
9. 不要在过滤器里起 Godot、读 `.godot/`、或根据 V5 stdout 有没有 `CONFIG_ALIVE` 做分支。
10. 不要因为滤掉了 Config 就把该脚本从「可能还有编译问题」中移除。
11. 不要给 shader 走 escalate；也不要每个 GDScript patch 都附带 V3。V3 只由 §2.1 触发表或收尾门启动（N07 / N15）。
12. 不要尝试用过滤器「发现」单条伪造 UID；发现不了（N06）。
13. 不要每轮无条件跑 V3。`require_warm_cache` ≠ `import_every_verify`。
14. 不要对 pointer 的 `res_path`（引用方）跑 V2，只对 `target_res_path` 跑。
15. 不要把 R8/合并逻辑写进 `filter_verify_output`。
16. 不要只跑一轮 V1：修完 pointer 根因后必须再 V1。
17. 不要把「跑过收尾 V3」当成迁移完成；V3 打出新根因要回 Agent。

---

## 12. 与外壳的分界（避免把过滤器写成半个 runner）

过滤器 **不实现**、但实现过滤器的人必须假定外壳已经保证：

| 外壳必须做 | 依据 | 若没做，过滤器会怎样 |
| --- | --- | --- |
| 禁 `--debug`，`start_new_session` + `killpg` | N08 | 挂死/signal 11，过滤器收不到完整日志 |
| 缓存不变量：没有 `global_script_class_cache.cfg` 才 V3；已 WARM 则复用 | N03 | 在 COLD 上跑 V1/V2 时，class_name 假阳性会被当成真缺失 |
| 本轮是否 V3 只看 §2.1 触发表（`^[+-]class_name\s` / shader 后缀或 hunk） | N03 N01 N06 | 每轮无条件 import 只烧时间；autoload FP 不会因此消失 |
| 入队在**隔离 workspace** `rm **/*.uid` 再 V3 **一次**；禁止改用户原仓 | N06 | 静默错误 UID 永远漏报 |
| 成功判定：单次看 FilterResult；项目级看根因+未消化 pointer；INFRA_FAILURE 仅外壳 | N08 | 用单次 CLEAN 当项目完成会漏掉样例 F 这类 pointer |
| V1 → 对 `target_res_path` 跑 V2 → `merge_command_results` → **再 V1 直到 pointer 稳定** | N04 N08 | 哨兵提前结束后 autoload/深层 preload 永远看不见 |
| shader / UID：触发表或收尾门才 V3；收尾打出根因则回 Agent | N07 N15 | 漏检 shader；或把未修完的仓库标完成 |
| 工作区串行锁 | 先验 N14 | 缓存互踩 |
| 拒收 `*.csproj` / `*.gdextension` | 先验 N13 | 不在本过滤器职责内 |

---

## 13. 建议的文件布局（生成代码时按此切，不要揉成一个 800 行 rules.py）

生产包就是 `codebase_index/godot_mcp/src/godot_mcp/verify_filter/`。
`run_verify_tool` 直接调用本包三个入口，不再经过旧的 `noise_filter.apply_noise_filter`
适配器（该目录已删除，避免第二套 `passed`/`issues` 契约误导调用方）。推荐按模块切：

```text
<pkg>/verify_filter/
  __init__.py          # filter_verify_output, merge_command_results, parse_autoload_keys
  models.py
  parse.py
  signature.py
  autoload.py
  pipeline.py          # 只编排 §7.1–§7.8
  merge.py             # §7.10
  rules/
    protect.py
    sentinel.py
    autoload_fp.py
    cascade.py
    wrappers.py
    uid_cluster.py
    infra.py
tests/fixtures/godot_4_7_1/*.log
tests/test_parse.py
tests/test_signature.py
tests/test_autoload_keys.py
tests/test_rules_*.py
tests/test_pipeline_golden.py
tests/test_merge.py
```

MCP `verify` 的返回值是 `VerifyGateResult`（过滤视图 + Gate 判定），不是旧的
`{"passed", "issues"}`。单次 `FilterResult.status == CLEAN` 只表示这一份日志无根因，
不是项目级完成（§9）。LSP 方案已整体删除，不存在 `filter_lsp_diagnostics`。

---

## 14. 完成定义

过滤器实现完成，当且仅当：

1. §10 全部黄金测试绿。
2. 任意一条 `protected` 文案在带齐全白名单时仍出现在 `root_cause_errors`。
3. 样例 C 过滤后 `root_cause_errors` 为空，且 `untrusted_files` 含 `main.gd` 与 `uses_autoload.gd`。
4. 样例 I 的 `root_cause_errors` 长度为 1，message 含 `UID duplicate detected`。
5. 样例 A 包装行是 dropped，不是 root_cause（R4 不得因 R2 升级）。
6. 样例 F：`target_res_path == res://root_bad.gd` 且 `res_path == res://dep_1.gd`，`status=CLEAN`。
7. 代码路径上不存在 `exit_code == 0` → 项目级通过的短路。
8. 没有调用 Godot、没有 `--debug`、没有按 V5 输出分支；改 role 只用 `replace`。

做到以上即可：`root_cause_errors` 接 Agent reward；`pointers.target_res_path` 接 V2；`merge_command_results` 接项目级是否完成；`symptoms` 接 LLM；`untrusted_files` 接 caveat。
