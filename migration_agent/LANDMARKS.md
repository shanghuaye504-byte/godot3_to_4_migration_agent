# 宿主与命令行：实现路标

[全项目执行顺序](../LANDMARKS.md) · [全项目问题总账](../DEFECTS.md) · [上级文档](../LANDMARKS.md) · [本级问题](../migration_agent/DEFECTS.md)

更新：2026-10-17。以当前代码为现状；下文未勾选项均为待修复/待开发。**按根目录 S00→S25 执行，到本目录时再展开；本级编号不重新从 1 开始。**

## 宿主的最小公共约定

当前目录及四个子包只有骨架。下面文件均是**待新增**，不是现成 API：`config.py`、`cli.py`、`context.py`；子模块具体落点见下级文档。

`MigrationConfig` 统一 source/output/state/artifacts 路径、目标引擎版本及可执行文件、RAG 配置、模型标识、max_rounds/max_tool_steps/max_cost、各执行模式超时与 Godot 槽位上限。宿主字段可自定，但转换成底层 Config 时只能使用真实字段名。

`RunContext` 持 run_id、独立 StateStore、项目 Config、索引连接、TraceStore、预算器和锁。单工作区工具串行；不要通过修改进程全局环境切换正在运行的多个仓库。

## 包与 CLI

根 pyproject 统一管理 `migration_agent` 和 `inline_tools` 包发现，并纳入 path 依赖 codeindex/godot-mcp/rag；build/dev/test 依赖放 dependency-groups，不在本目录再建 pyproject。编排用 LangGraph 时在根声明实际运行依赖及选定模型适配器，接入前按官方版本完成契约测试。

统一入口 `migrate-agent`，子命令随阶段逐步开放：run（S18）、run --resume（S19）、mutate（S21）、judge（S22）、batch（S24）。尚未实现的命令返回明确提示，不能返回迁移成功。S14 先支持 --help/config 检查及程序化适配测试。

## 状态与目录

运行结果使用 RUNNING/CLEAN/PARTIAL/ESCALATED；运行无效另记录 invalid_reason，不混进模型修复失败率。state/report 放在 Agent 项目之外的受管运行目录；跨仓 fix-cache 使用单独共享路径。源仓库始终不作为修改目标。

## 观测配置随宿主一起落地

S14 开始就配置 OpenTelemetry SDK → Collector → Langfuse/Phoenix，不等 Agent 完成再补埋点。新增 observability profile、endpoint、OTLP HTTP 协议、语义版本、采样与导出超时，凭据仅环境引用；RunContext 持 tracer 和 run/span 映射，SQLite 仍是恢复/成本权威。具体职责和反例见 [观测契约](trace/LANDMARKS.md)。

## 恢复方案只有一个入口

S18 使用 LangGraph 原生持久化 checkpoint；S19 的 resume.py 只做外部副作用核验，再用原 thread_id 续跑。MigrationConfig 保存 checkpoint 目录及 graph/schema 版本，RunContext 持本进程新建的 saver 连接。根依赖增加 langgraph-checkpoint-sqlite；首版每 run 独立文件、串行执行，不把本地 SQLite 描述成多机共享执行后端。具体分工见 [恢复契约](orchestrator/LANDMARKS.md)。

## 下级导航

- [确定性预处理](l0/LANDMARKS.md)
- [单仓编排](orchestrator/LANDMARKS.md)
- [轨迹、预算与恢复](trace/LANDMARKS.md)
- [独立评测与批处理](eval/LANDMARKS.md)

## 本目录执行清单

<a id="s00"></a>

### S00：固定环境、真实接口与观测配置

- [x] 完成 [S00](../LANDMARKS.md) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：先做现有组件导入与配置/引擎/产物预检，记录版本。宿主可安装 CLI 到 S14 再实现，这里不用提前造占位业务。

**交付物**：交付环境检查结果与真实契约反例。

**验收**：依赖/引擎缺失明确失败，现有 loader 的异 CWD 行为有测试。

<a id="s01"></a>

- [ ] **S01 · 先建最小独立评测器与观测契约测试**：[独立评测与批处理](eval/LANDMARKS.md)、[轨迹、预算与恢复](trace/LANDMARKS.md)；先完成根队列的前置步骤，验收看负责目录。

<a id="s13"></a>

- [ ] **S13 · 修检索配置、符号提取和 OTel 观测事件**：[轨迹、预算与恢复](trace/LANDMARKS.md)；先完成根队列的前置步骤，验收看负责目录。

<a id="s14"></a>

### S14：实现宿主、SQLite 账本与 OTel 双后端接线

- [ ] 完成 [S14](../LANDMARKS.md) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：负责根包/CLI/config/context；新增 observability 配置和凭据环境引用，OTel SDK 与 OTLP HTTP exporter 在根声明依赖。后端实验客户端按 eval 依赖组管理，不在子包新建 pyproject。

**交付物**：交付安装/预检、共享 RunContext 和 offline/双后端 profile；TraceStore 与 tracer 注入工具，避免多次初始化 provider。

**验收**：异 CWD、未知键拒绝、版本/endpoint/凭据缺失分类；离线不联网，双后端模式不能把未配置冒充已联通。

**问题详情与复现**：[ORC-01 · 宿主若照旧签名封装，工具无法完成一次调用](orchestrator/DEFECTS.md)；[TRC-01 · 按 repo_id 保存一行，无法区分试验和多个补丁](trace/DEFECTS.md)；[TRC-04 · 只给成功轮次记成本，预算与可观测性不完整](trace/DEFECTS.md)；[TRC-05 · 缺少统一调用链，检索、补丁与引擎失败无法关联](trace/DEFECTS.md)。

**具体落点**：[单仓编排](orchestrator/LANDMARKS.md)、[轨迹、预算与恢复](trace/LANDMARKS.md)。

<a id="s15"></a>

- [ ] **S15 · 实现隔离 intake 与 L0 事务边界**：[确定性预处理](l0/LANDMARKS.md)；先完成根队列的前置步骤，验收看负责目录。

<a id="s16"></a>

- [ ] **S16 · 增加小白名单 codemod 和可结案陷阱扫描**：[确定性预处理](l0/LANDMARKS.md)；先完成根队列的前置步骤，验收看负责目录。

<a id="s17"></a>

- [ ] **S17 · 实现补充资源扫描与完整成功条件**：[单仓编排](orchestrator/LANDMARKS.md)；先完成根队列的前置步骤，验收看负责目录。

<a id="s18"></a>

- [ ] **S18 · 接通单仓编排、原生 checkpoint 与有界路由**：[单仓编排](orchestrator/LANDMARKS.md)、[轨迹、预算与恢复](trace/LANDMARKS.md)；先完成根队列的前置步骤，验收看负责目录。

<a id="s19"></a>

- [ ] **S19 · 实现 checkpoint 恢复与外部副作用对账**：[轨迹、预算与恢复](trace/LANDMARKS.md)、[单仓编排](orchestrator/LANDMARKS.md)；先完成根队列的前置步骤，验收看负责目录。

<a id="s20"></a>

- [ ] **S20 · 增加共享修复缓存**：[轨迹、预算与恢复](trace/LANDMARKS.md)；先完成根队列的前置步骤，验收看负责目录。

<a id="s21"></a>

- [ ] **S21 · 扩展变异、复验 RAG 并接入平台实验**：[独立评测与批处理](eval/LANDMARKS.md)、[轨迹、预算与恢复](trace/LANDMARKS.md)；先完成根队列的前置步骤，验收看负责目录。

<a id="s22"></a>

- [ ] **S22 · 实现独立 Judge、人工校准与关联标注**：[独立评测与批处理](eval/LANDMARKS.md)；先完成根队列的前置步骤，验收看负责目录。

<a id="s23"></a>

- [ ] **S23 · 完成平台对比实验、baseline 与消融报告**：[独立评测与批处理](eval/LANDMARKS.md)、[轨迹、预算与恢复](trace/LANDMARKS.md)；先完成根队列的前置步骤，验收看负责目录。

<a id="s24"></a>

- [ ] **S24 · 实现进程池批处理、上下文传播与限流**：[独立评测与批处理](eval/LANDMARKS.md)、[轨迹、预算与恢复](trace/LANDMARKS.md)；先完成根队列的前置步骤，验收看负责目录。

<a id="s25"></a>

- [ ] **S25 · 验收崩溃恢复、观测降级并完成清理**：[独立评测与批处理](eval/LANDMARKS.md)、[轨迹、预算与恢复](trace/LANDMARKS.md)；先完成根队列的前置步骤，验收看负责目录。

## 完成一项怎么记

在相关 DEFECTS 条目附测试名称/命令、实际结果与版本；只勾本步验收通过的项目。涉及代码的目录同步 README。L3 草稿放本地 DESIGN_NOTES；跨模块有后果的决定落 docs/adr。文档修订完成不等于业务修复完成。
