# 架构决策记录

本目录记录跨模块设计决定，已发布的决策只增不改；后续替代方案另写新记录。记录被采纳不表示代码已实现。

- [ADR-0001：原生 checkpoint 与外部副作用对账](0001-langgraph-checkpoints-and-external-effects.md)：图状态、代码修改、预算、批处理和观测的恢复边界。

执行顺序见 [根路标](../../LANDMARKS.md)，具体契约见 [编排路标](../../migration_agent/orchestrator/LANDMARKS.md#checkpoint-contract)。
