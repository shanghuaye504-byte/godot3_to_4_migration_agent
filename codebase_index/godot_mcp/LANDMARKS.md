# Godot 验证栈：实现路标

[全项目执行顺序](../../LANDMARKS.md) · [全项目问题总账](../../DEFECTS.md) · [上级文档](../LANDMARKS.md) · [本级问题](DEFECTS.md)

更新：2026-10-17。以当前代码为现状；下文未勾选项均为待修复/待开发。**按根目录 S00→S25 执行，到本目录时再展开；本级编号不重新从 1 开始。**

## 现有验证链要保留

`run_verify_tool` → `collect_workspace_view` → `run_verify(V1/V2/V3)` → filter/merge → `evaluate`。

- V1：生成 `__probe_sentinel.gd`，preload 枚举到的 `.gd`，随后 check-only 解析。
- V2：对 pointer 指向的目标脚本做局部解析；不是改调用方来代替根因。
- V3：editor/import，参与 shader、UID 和 class cache 处理。`shader_checked=True` 只表示该阶段执行过，不证明所有渲染行为。

使用 `run_verify_tool(kind, target=None, *, config, gate_cfg, state_store, ...)`。实际决策是 CONTINUE、NO_PROGRESS_WARN、FILE_STUCK_WARN、OSCILLATION_ESCALATE、BUDGET_EXCEEDED、CIRCUIT_OPEN。升级模型和补丁回滚由宿主 S18 实现。

## 不要混淆状态

局部 check_file 不消费全库轮次；每 run 使用独立 StateStore。基础设施 TIMEOUT/CRASH 与脚本错误分开。OPEN 后先短路，不继续跑引擎。只有显式新 run/重置才解除。

快照用于观察 diff 与重导触发；它没有恢复文件的能力。源码恢复和 trace 对账归 S19。补充 sweep 由宿主 S17 提供固定模式，不能把自由 argv 暴露出去。

## 测试入口

`uv run --project codebase_index/godot_mcp pytest codebase_index/godot_mcp/tests -q`。先注入 run_verify_fn 测控制流，再使用 S00 锁定的引擎跑 S01 案例；模拟通过和引擎实测分别记录。

## 宿主恢复接线

现有 InMemoryStateStore 是进程内实现，不自带跨进程恢复。S11 先隔离每 run；S18 将完整 Gate 状态与图 checkpoint 对接，S19 校验重入回执避免重复累计历史。底层 Gate 不另引入全局 checkpoint/saver，运行句柄仍由宿主注入，详见 [恢复契约](../../migration_agent/orchestrator/LANDMARKS.md#checkpoint-contract)。

## 本目录执行清单

<a id="s09"></a>

### S09：隔离局部检查、修熔断和阈值接线

- [ ] 完成 [S09](../../LANDMARKS.md#s09) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：局部检查不进入全库历史；OPEN 在启动 Godot 前短路；入口注入实际 RetryGateConfig。

**交付物**：交付稳定的 VerifyGateResult；继续使用真实 decision 枚举，明确重置策略。

**验收**：全库 A→局部空→全库 A 不假震荡；真全库循环会停；OPEN 后 spawn=0；自定义阈值生效。

**问题详情与复现**：[VER-01 · 局部检查污染全库历史，造成假震荡](DEFECTS.md#ver-01)；[VER-02 · 熔断已 OPEN，下一次健康输出又允许继续](DEFECTS.md#ver-02)；[VER-03 · retry_gate YAML 没接到默认工具入口](DEFECTS.md#ver-03)。

<a id="s10"></a>

### S10：补验证快照与重导触发范围

- [ ] 完成 [S10](../../LANDMARKS.md#s10) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：快照包含实际编辑后缀；识别内嵌 shader/项目配置、class_name 与重复 UID 双端修复。

**交付物**：交付差异可见性及按需 V3 触发。快照仍只作观察，不充当文件恢复协议。

**验收**：逐后缀 diff、UID 两端与 class 声明变体；用注入 spawn 验证 V3 次数，再补真实引擎检查。

**问题详情与复现**：[VER-04 · 快照漏场景/项目配置，相关修改无法驱动重导](DEFECTS.md#ver-04)；[VER-05 · class_name 与重复 UID 的重导触发有盲区](DEFECTS.md#ver-05)。

<a id="s11"></a>

### S11：绑定每次运行的状态、锁和索引同步

- [ ] 完成 [S11](../../LANDMARKS.md#s11) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：隔离每 run StateStore，串行状态读改写；向宿主明确生命周期锁与 verify 锁的嵌套方式。

**交付物**：交付状态/锁边界测试；不在此模块复制宿主或编辑器。

**验收**：顺序复用 worker 不串状态，重复接管被拒，不发生锁自死。

**问题详情与复现**：[VER-06 · 全局单槽状态和锁范围不适合多次仓库运行](DEFECTS.md#ver-06)。

## 完成一项怎么记

在相关 DEFECTS 条目附测试名称/命令、实际结果与版本；只勾本步验收通过的项目。涉及代码的目录同步 README。L3 草稿放本地 DESIGN_NOTES；跨模块有后果的决定落 docs/adr。文档修订完成不等于业务修复完成。
