# 轨迹、预算与恢复：问题与复现

[全项目执行顺序](../../LANDMARKS.md) · [全项目问题总账](../../DEFECTS.md) · [上级文档](../DEFECTS.md) · [本级路标](../trace/LANDMARKS.md)

按执行顺序排列。**已复现/源码确认**指已有代码证据；**规划风险**指组件尚未实现，复现描述是先要写下的失败测试。所有代码修复仍未完成，不能把新文档当作修复结果。

## 本级负责的问题

复现均在临时项目/数据库执行；需要 Git 时先提交干净来源，注入成功 sync；需要引擎的条目先完成 S00。源码链接用于定位，精确函数名写在正文，避免依赖易漂移行号。

<a id="trc-01"></a>

### TRC-01：按 repo_id 保存一行，无法区分试验和多个补丁

**顺序 / 状态**：[S14](../../LANDMARKS.md)；规划风险；存储待实现。

**范围与原因**：同一仓库要跑 baseline、消融和重复试验；一轮也可能有多次失败编辑。旧 schema 用 repo_id 主键、每轮单个 patch 字段，会覆盖历史。

**具体表现**：同仓库先 with-RAG 再 without-RAG，第二次启动覆盖前一 run 的状态。

**如何复现**：在临时 SQLite 执行旧设计建表，插入相同 repo_id 的两个独立实验；观察主键冲突，或用 upsert 后前一次记录丢失。

**修复办法**：runs 用独立 run_id；rounds 用 (run_id, round_idx)；patch_attempts 和 events 独立 ID。保留拒绝/回滚及原始日志引用，外键和唯一约束由事务维护。

- [ ] **验收测试**：同 repo 两个 run 可并存，一轮三个 attempt 不丢失；事件可追溯到工具、patch、规则和验证。

**关键源码**：[__init__.py](__init__.py)、[models.py](../../codebase_index/godot_mcp/src/godot_mcp/verify_gate/models.py)。

<a id="trc-04"></a>

### TRC-04：只给成功轮次记成本，预算与可观测性不完整

**顺序 / 状态**：[S14](../../LANDMARKS.md)；规划风险；账本待实现。

**范围与原因**：没有 commit 的模型失败、工具拒绝和 Judge 调用也会花钱。只在 round 成功后累计，既漏计成本，也无法事前阻止超额。

**具体表现**：两次 LLM 重试都失败、没有 patch，但 API 已计费；旧 round_traces 可能仍显示成本 0。

**如何复现**：先用假模型返回两次失败 usage、一次成功 usage，随后模拟 guard 拒绝；检查设计账本是否仍记录所有调用和费用。当前无实现，应以先失败测试固定需求。

**修复办法**：每次模型调用先预留上限，结束以实际 usage/定价版本结算；失败且 usage 未知单独标 unknown。记录工具/RAG/verify 事件与日志引用，不能把审计写失败吞成成功。

- [ ] **验收测试**：重试、拒绝、Judge、缓存命中各有事件；预算不足时调用数为 0；多币种/未知价格不伪造美元零成本。

**关键源码**：[__init__.py](__init__.py)、[observe.py](../../rag/retriever/observe.py)。

<a id="trc-05"></a>

### TRC-05：缺少统一调用链，检索、补丁与引擎失败无法关联

**顺序 / 状态**：[S14](../../LANDMARKS.md)；新增规划风险；OTel 和后端尚未接入。

**范围与原因**：trace 包只有骨架，旧规划仅覆盖 SQLite 事件，没有 OpenTelemetry span、上下文传播或 Langfuse/Phoenix 接线。同一轮可能检索多次、重试模型、拒绝补丁，孤立日志不足以解释最终结果。

**具体表现**：一次缓存命中后模型生成坏补丁，guard 拒绝，随后 verify 超时；若只记 round 总耗时，就无法区分检索、模型、守卫还是引擎导致失败。

**如何复现**：先新增离线契约测试：用内存 exporter 驱动 fake 检索→模型→拒绝编辑→超时验证，断言共享 run_id、正确父子 span 和各自状态；当前 trace 骨架不能生成这些记录，测试应先失败。S14 再用本地假 OTLP 接收器复现断网和超时。

**修复办法**：按本级 LANDMARKS 的 otel-contract 建单一 OTel 埋点，经 Collector 输出到 Langfuse/Phoenix；SQLite 保存 trace/span 与 call/attempt 的映射。自定义 span 和框架埋点只选一个负责同一次模型调用，缓存命中仍保留检索 span。

- [ ] **验收测试**：内存导出器断言调用树、拒绝/超时/缓存状态和脱敏；假接收器断言 OTLP HTTP 与有界队列；真实两后端可按同一 trace_id 找到一次运行且无重复模型 span。

**关键源码**：[__init__.py](__init__.py)、[observe.py](../../rag/retriever/observe.py)、[cache.py](../../rag/retriever/cache.py)。

<a id="trc-02"></a>

### TRC-02：Git、副作用账本与图 checkpoint 之间有崩溃窗口

**顺序 / 状态**：[S19](../../LANDMARKS.md)；规划风险；恢复协议待实现。

**范围与原因**：LangGraph checkpoint 保存图执行状态，不与 Git 提交或业务 SQLite 构成同一事务。节点可能已写文件/提交成功，但返回值还没进入 checkpoint；失败节点恢复时可能重新执行。

**具体表现**：edit 已生成提交 C，但 apply 节点在保存结果前被 kill；checkpoint 仍停在 apply 之前。仅恢复图就再调 edit，可能重复补丁或遇到脏树。

**如何复现**：在临时仓库先持久化 prepare 的 operation_id/预期 SHA，再调用 edit；分别在 apply-index 后、commit 后、验证完成后和下一 checkpoint 写入前故障退出。新进程用同一 thread_id 恢复，检查是否重改、重复 commit 或重置 Gate 历史。另模拟模型服务已收请求但结果未持久化。

**修复办法**：图恢复用原生 checkpointer；副作用用稳定 operation_id、PREPARED/PATCH_COMMITTED/VERIFIED/RECORDED 和前后 SHA/文件指纹对账。已证明完成则节点返回持久化回执，未发生才执行，未知脏树停止。模型响应已保存可复用，服务端执行但本地无回执时标 UNKNOWN 并保守保留预算，不承诺外部调用恰好一次。

- [ ] **验收测试**：覆盖上述四个崩溃点和副作用回执已落盘但 checkpoint 未落盘的窗口；受控补丁无重复副作用、本地计费事件去重、Gate 历史不清零、已完成基线不重冻。未知模型费用不写零，未知工作树明确拒绝。

**关键源码**：[git_txn.py](../../inline_tools/editandfixguard/git_txn.py)、[models.py](../../codebase_index/godot_mcp/src/godot_mcp/verify_gate/models.py)、[__init__.py](__init__.py)。

<a id="trc-06"></a>

### TRC-06：观测导出与恢复混用会丢账，进程切换还会断链

**顺序 / 状态**：[S19](../../LANDMARKS.md)；新增规划风险；恢复和导出未实现。

**范围与原因**：OTel 批量导出通常是异步的，存在采样、断网和进程退出丢失的可能；它不能充当预算或恢复账本。进程池不会凭空继承有效上下文，崩溃后也不能继续一个已经中断的 span。

**具体表现**：模型已经产生费用，但 exporter 断网；若根据后端 span 累计预算就漏账。恢复时换一个 worker，若只传 run_id，则新 trace 与原运行没有明确关联。

**如何复现**：S14 用假 exporter 持续超时并执行一次有 usage 的模型调用，断言 SQLite 仍有结算；S19 在 commit 后中断再恢复，检查原 run_id 保留且新 trace 用 Span Link 指向旧 span；S24 用 spawn 子进程验证 traceparent 的注入/提取。以上是待实现能力的失败对照。

**修复办法**：本地事务先持久化；观测使用有界异步导出和明确的丢弃/失败计数。恢复创建新 trace，关联原 run_id 和旧 span；worker 自建 provider/exporter，任务信封传 W3C 上下文，退出有界 flush/shutdown。

- [ ] **验收测试**：断网不改变恢复和预算事实；持续失败不无限阻塞任务；新进程可关联调用，崩溃后的未完成节点有中断标记；eval 导出失败须标证据不完整，不能声称两后端验收成功。

**关键源码**：[__init__.py](__init__.py)、[__init__.py](../eval/__init__.py)。

<a id="trc-03"></a>

### TRC-03：每仓本地缓存不能跨仓复用，短 key 又可能复用错修复

**顺序 / 状态**：[S20](../../LANDMARKS.md)；规划风险；缓存待实现。

**范围与原因**：每工作区 trace.db 各自独立，没有共享缓存；错误签名和一行代码也不足以确定版本、对象和提示上下文相同。

**具体表现**：两个仓库都有 .instance()，一个是 PackedScene，另一个是自定义类；过短 key 将同一补丁用到两者。

**如何复现**：设计反例：两个独立 trace DB 写入相同 key，确认互不可见；再给不同 target_version/owner 的查询计算旧 key，观察碰撞。

**修复办法**：独立共享缓存库，与每 run trace 分开。key 包含版本、模型/提示/工具契约、规则/语料指纹和必要上下文。命中只是候选，仍走锚定、守卫和验证；失败不重复投喂。

- [ ] **验收测试**：同条件可命中，版本/owner/模型变更不命中；并发写有超时重试；失效候选被隔离。

**关键源码**：[__init__.py](__init__.py)、[cache.py](../../rag/retriever/cache.py)。
