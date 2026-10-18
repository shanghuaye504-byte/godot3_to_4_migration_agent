# `migration_agent/orchestrator` — L1/L2 LangGraph ReAct 修复编排器

当前只有包骨架，以下均为待实现职责：LangGraph 修复循环、根因分析、七个工具适配、有界模型路由及补充资源验证。

图状态恢复采用原生持久化 checkpointer；Git/SQLite 对账处理图外副作用，不另造图调度器。按 [LANDMARKS](LANDMARKS.md) 的 S18/S19 与[恢复契约](LANDMARKS.md#checkpoint-contract) 实现；问题与复现见 [DEFECTS](DEFECTS.md)。
