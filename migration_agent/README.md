# `migration_agent` — Godot 3→4 批量迁移收尾 Agent 主控包

本目录是 Godot 3→4 游戏项目迁移 Agent 的宿主骨架；尚未实现完整编排、持久化 checkpoint 或恢复。后续通过进程内库调用组合 RAG、代码库索引、受控编辑和真实引擎验证。

按 [LANDMARKS](LANDMARKS.md) 执行，问题见 [DEFECTS](DEFECTS.md)。恢复统一采用 LangGraph 原生 checkpoint 管图状态、Git/业务 SQLite 核对外部操作、父进程监督批处理；[具体契约](orchestrator/LANDMARKS.md#checkpoint-contract) 与 [ADR-0001](../docs/adr/0001-langgraph-checkpoints-and-external-effects.md) 保持一致。

## 环境预检

S00 的预检在仓库根的 uv 环境里运行，不在本目录另建虚拟环境。示例配置是 [env.preflight.example.yaml](env.preflight.example.yaml)。`GODOT_BINARY` 未设置时使用 `/usr/local/bin/godot4`。

```bash
uv run python -c "from migration_agent.preflight import run_preflight; print(run_preflight('migration_agent/env.preflight.example.yaml'))"
uv run pytest migration_agent/tests/test_s00_preflight.py -q
```

预检核对 Python、tree-sitter、Godot、规则库与语料指纹，并检查观测配置的格式。`offline` 不要求后端在线；`dual` 只校验地址，不连接 Langfuse 或 Phoenix。命令行 `migrate-agent` 和 OpenTelemetry SDK 留到 S14。

## 子模块概览

- [l0](l0/README.md)：受控预处理、转换、索引和一次性基线冻结。
- [orchestrator](orchestrator/README.md)：修复图、原生 checkpoint 和分层验证。
- [trace](trace/README.md)：审计、预算、saver 工厂、外部对账和观测。
- [eval](eval/README.md)：独立评测、平台实验及批处理监督。
