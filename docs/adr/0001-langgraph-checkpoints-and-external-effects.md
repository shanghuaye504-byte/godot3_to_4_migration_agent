# ADR-0001：使用原生 checkpoint 恢复图，对账外部副作用

日期：2026-10-17。状态：已采纳的实现规划，尚未实现。

## 问题

旧路标写了 Git/SQLite 对账，却没有明确 LangGraph 原生 checkpointer。简历据此只写 Git/SQLite 恢复，会让读者以为项目自行实现图状态恢复；反过来，直接改成“checkpoint 自动恢复一切”也不成立。

当前 orchestrator/trace 只有包骨架，Gate 默认 InMemoryStateStore 退出即失效。需要同时定义图状态恢复、外部副作用和 worker 监督，避免出现两套图调度器。

## 决定

1. **图状态用原生实现**：单机首版使用 SqliteSaver，thread_id=run_id，durability="sync"；每 run 独立 checkpoint 文件，每工作区单一执行者。S18 接入，S19 验收完整故障恢复。图版本与状态 schema 固定，恢复不兼容时拒绝。
2. **外部副作用单独核验**：Git 保存代码；业务 SQLite 保存操作回执、验证、成本和审计。检查点、业务库与 Git 不处于同一事务。稳定 operation_id 及提交标记/文件指纹使失败节点重入时能识别已完成修改；回滚遵守同一机制。
3. **不重复保存图调度状态**：目标、提案、必要消息和完整 Gate 状态由 checkpoint 管理，审计表不另写可驱动恢复的 last_node。业务账本负责预算事实，图内摘要不作为新的可花额度。
4. **批处理负责运行监督**：父进程清理进程组和槽位，持久化任务并重新调度原 run；新 worker 重建句柄，持锁后以同一 thread_id 对账并恢复。原生 checkpoint 不归还信号量或启动 worker。
5. **观测不决定恢复**：新恢复进程可创建新 OTel trace，用业务 ID 和 Span Link 关联历史；不改变 run_id/thread_id，不根据后端是否收到 span 判定操作是否完成。

## 例子与边界

apply 已提交 C，节点结果尚未保存就崩溃；原 checkpoint 仍在 apply 前。恢复时节点可能再执行，必须先根据 operation_id 核验 C，再返回已有回执，避免重复应用 diff。将操作包成 task 有助于复用已保存结果，但未完成 task 仍可能重跑。

模型服务已执行、响应未持久化时，框架不能证明是否收费；优先使用服务支持的查询/幂等能力，否则标未知、保留预算，并按策略停止或有限重试。保证可核验的受控补丁去重，不宣称所有外部调用恰好一次。

checkpoint 也不回退磁盘文件。历史快照重放仅在隔离副本中调试；正常恢复读取最新快照。L0 在图外按阶段证据恢复，不重做已完成转换或冻结，未知状态停止。

## 后果与验收

接受本地 SQLite 的单机范围，不把它作为多机共享执行方案；跨机部署另立决策。会增加 saver 接线、序列化、回执幂等和故障注入测试，但不需实现自定义 checkpointer。

S18 测全新进程恢复图；S19 测修改/commit/verify/checkpoint 间崩溃；S24/S25 测 worker kill、互斥接管与进程/槽位回收。详细入口及测试门见 [原生恢复契约](../../migration_agent/orchestrator/LANDMARKS.md#checkpoint-contract) 和 [TRC-02](../../migration_agent/trace/DEFECTS.md#trc-02)。

依据：[LangGraph checkpointer 与持久化模式](https://docs.langchain.com/oss/python/langgraph/checkpointers)、[任务重入与幂等约束](https://docs.langchain.com/oss/python/langgraph/functional-api)。
