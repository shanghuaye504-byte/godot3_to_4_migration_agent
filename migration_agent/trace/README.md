# `migration_agent/trace` — 本地 SQLite 轨迹存储与报告生成

当前只有包骨架。待实现职责：业务 SQLite 审计与预算、原生 SqliteSaver 工厂、外部副作用对账、共享修复缓存及报告；同时接入 OTel 与 Langfuse/Phoenix。

每 run 的图检查点与审计库分开。图状态/下一节点由 LangGraph 恢复，Git 与业务库核对修改/验证/费用；OTel 不作为恢复来源。开发按 [LANDMARKS](LANDMARKS.md)，职责见[恢复契约](../orchestrator/LANDMARKS.md#checkpoint-contract)，反例见 [DEFECTS](DEFECTS.md)。
