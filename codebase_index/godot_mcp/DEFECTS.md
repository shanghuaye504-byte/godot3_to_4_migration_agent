# Godot 验证栈：问题与复现

[全项目执行顺序](../../LANDMARKS.md) · [全项目问题总账](../../DEFECTS.md) · [上级文档](../DEFECTS.md) · [本级路标](LANDMARKS.md)

按执行顺序排列。**已复现/源码确认**指已有代码证据；**规划风险**指组件尚未实现，复现描述是先要写下的失败测试。所有代码修复仍未完成，不能把新文档当作修复结果。

## 本级负责的问题

复现均在临时项目/数据库执行；需要 Git 时先提交干净来源，注入成功 sync；需要引擎的条目先完成 S00。源码链接用于定位，精确函数名写在正文，避免依赖易漂移行号。

<a id="ver-01"></a>

### VER-01：局部检查污染全库历史，造成假震荡

**顺序 / 状态**：[S09](../../LANDMARKS.md#s09)；已复现；代码待修。

**范围与原因**：check_file 与 check_workspace 共用 evaluate，它们的检查范围却不同。局部空错误不能作为全库历史中的空错误。

**具体表现**：全库 {A,B} → 检查一个干净文件 ∅ → 全库 {A,B}，当前触发 OSCILLATION_ESCALATE。

**如何复现**：用现有 verify_gate/helpers 的 make_state/make_view/make_request 构造上述三轮并调用 evaluate；再用注入 run_verify_fn 的工具层测试覆盖相同序列。

**修复办法**：局部结果不增加全库 rounds/signature_history/per-file 计数；基础设施失败走独立计数，成功时按明确策略清零。返回实际 VerifyGateResult，不引入旧 GateOutput。

- [ ] **验收测试**：先写工具层序列反例；保留真正全库 A→B→A 应停止的正例。

**关键源码**：[tool.py](src/godot_mcp/verify_gate/tool.py)、[algorithm.py](src/godot_mcp/verify_gate/algorithm.py)。

<a id="ver-02"></a>

### VER-02：熔断已 OPEN，下一次健康输出又允许继续

**顺序 / 状态**：[S09](../../LANDMARKS.md#s09)；已复现；代码待修。

**范围与原因**：算法只检查连续失败计数，没有入口短路已有 OPEN；工具层也先启动进程再判 Gate。

**具体表现**：3 次 CRASH 后状态为 OPEN；再传健康输出，decision 却是 CONTINUE、hard_stop=False。

**如何复现**：用 Gate helper 连续构造三次 infra_status=CRASH，再构造 OK，检查 state.circuit_state 与结果。

**修复办法**：OPEN 在工具启动子进程前短路；定义显式人工重置/新 run 重置，不能被单次成功偷偷关闭。返回完整结果并记录短路原因。

- [ ] **验收测试**：OPEN 后 spawn 调用次数为 0；显式重置后可恢复；失败达到阈值的临界轮数有测试。

**关键源码**：[algorithm.py](src/godot_mcp/verify_gate/algorithm.py)、[tool.py](src/godot_mcp/verify_gate/tool.py)。

<a id="ver-03"></a>

### VER-03：retry_gate YAML 没接到默认工具入口

**顺序 / 状态**：[S09](../../LANDMARKS.md#s09)；源码确认；代码待修。

**范围与原因**：run_verify_tool 无参调用 load_retry_gate_config，后者直接返回默认值。改共享配置不改变实际门控阈值。

**具体表现**：把 rounds_limit 设置为 2，默认工具仍按 40 轮记账。

**如何复现**：在临时配置写 retry_gate.rounds_limit=2，通过默认配置入口运行带桩验证；比较 remaining_budget.rounds_limit。显式注入 gate_cfg 可作为对照。

**修复办法**：宿主总是注入已校验的 gate_cfg；对外 MCP 启动时也从实际配置路径加载一次再传入。若给 Config 加路径字段，两个入口都要测试。

- [ ] **验收测试**：覆盖自定义阈值、默认阈值、未知键报错和非法阈值；配置示例只用现有字段。

**关键源码**：[tool.py](src/godot_mcp/verify_gate/tool.py)、[config.py](src/godot_mcp/verify_gate/config.py)、[server.py](src/godot_mcp/server.py)。

<a id="ver-04"></a>

### VER-04：快照漏场景/项目配置，相关修改无法驱动重导

**顺序 / 状态**：[S10](../../LANDMARKS.md#s10)；源码确认；代码待修。

**范围与原因**：source_snapshot 用于差异触发，不是恢复备份；当前后缀缺 .tscn 与 .godot，场景内嵌 shader 和项目配置变化可能不可见。

**具体表现**：只改 main.tscn 的内嵌 Shader 或 project.godot 的 autoload，快照差异可能为空。

**如何复现**：临时项目只含 main.tscn/project.godot，修改前后各 scan_workspace 再 diff_snapshots；检查是否出现两文件。

**修复办法**：补 .tscn/.godot 等实际会编辑的配置后缀，并为内嵌 shader、autoload/class cache 变化明确 V3 触发。真实文件回滚由宿主事务实现，不能声称加后缀就获得恢复能力。

- [ ] **验收测试**：断言差异可见、需要重导时 spawn V3；失败恢复另在 S19 测，不混为一个测试。

**关键源码**：[snapshot.py](src/godot_mcp/verify_shell/snapshot.py)、[trigger.py](src/godot_mcp/verify_shell/trigger.py)。

<a id="ver-05"></a>

### VER-05：class_name 与重复 UID 的重导触发有盲区

**顺序 / 状态**：[S10](../../LANDMARKS.md#s10)；源码确认；代码待修。

**范围与原因**：class_name 正则不识别同一行注解前缀；UID 簇只保留字典序较小路径用于触发，修改另一端可能不重导。

**具体表现**：重复 UID 出现在 a.tscn 和 z.tscn，修 z 时只匹配到 a，未触发需要的 V3。

**如何复现**：给 apply_uid_cluster_rule 输入两端路径的重复日志，再只构造 z 的 diff 调 is_uid_duplicate_repair；另测 +@tool class_name Foo 形式的 diff 行。

**修复办法**：保留 UID 两端并同时匹配；沿用真实 ClassifiedEvent(resource_error) 而非新增不存在的事件类。触发正则保留 +/-，类缓存扫描则识别源码行。

- [ ] **验收测试**：UID 两端各修一次都触发；普通警告不误触发；注解同行写法先由目标引擎/语法夹具确认合法再支持。

**关键源码**：[uid_cluster.py](src/godot_mcp/verify_filter/rules/uid_cluster.py)、[trigger.py](src/godot_mcp/verify_shell/trigger.py)、[class_cache.py](src/godot_mcp/verify_shell/class_cache.py)。

<a id="ver-06"></a>

### VER-06：全局单槽状态和锁范围不适合多次仓库运行

**顺序 / 状态**：[S11](../../LANDMARKS.md#s11)；已复现及源码确认；整合待修。

**范围与原因**：默认 StateStore 是全局单槽。workspace_lock 只包验证采集，evaluate/save 在锁外，edit 又不持同锁。目录隔离无法自动隔离进程内状态。

**具体表现**：同一 worker 先处理仓库 A 再处理 B，B 首次 check_file 的 round_index 为 2；并行工具调用还可能同时通过干净树检查。

**如何复现**：用同一个 InMemoryStateStore 对两个临时项目依次执行注入桩的 run_verify_tool，观察第二个轮次；并发测试用屏障暂停在 load/save 之间。

**修复办法**：每 run 注入独立 StateStore；宿主持生命周期锁阻止重复接管，并串行调度写与验证。load/采集/evaluate/save 的状态更新需在同一串行边界；避免重复持有同一非重入 flock。

- [ ] **验收测试**：测试顺序复用 worker、重复 resume、同工作区并发 edit/verify 与不同工作区互不阻塞。

**关键源码**：[state_store.py](src/godot_mcp/verify_gate/state_store.py)、[tool.py](src/godot_mcp/verify_gate/tool.py)、[lock.py](src/godot_mcp/verify_shell/lock.py)。
