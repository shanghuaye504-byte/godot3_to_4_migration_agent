# `migration_agent/eval` — Agent-as-Judge 与批处理评测套件

当前只有包骨架。按阶段实现独立验证器、真值隔离、反向变异、Judge/人工校准和对比实验，评分关联 Langfuse/Phoenix；先交付正常进程池批处理，再验收 worker 崩溃。

父进程负责清理进程/槽位和重排原 run；新 worker 使用同一 thread_id 接入原生 checkpoint 与外部副作用对账。具体顺序见 [LANDMARKS](LANDMARKS.md)，复现与验收见 [DEFECTS](DEFECTS.md)。
