# 独立评测与批处理：实现路标

[全项目执行顺序](../../LANDMARKS.md) · [全项目问题总账](../../DEFECTS.md) · [上级文档](../LANDMARKS.md) · [本级问题](DEFECTS.md)

更新：2026-10-17。以当前代码为现状；下文未勾选项均为待修复/待开发。**按根目录 S00→S25 执行，到本目录时再展开；本级编号不重新从 1 开始。**

## 按四次交付，不等到编排后才开始

1. S01：`cases.py/verifier.py` 最小固定样本和独立成功/失败/证据不足分类，先于智能编排。
2. S21：`reverse_mutator.py/metrics.py` 可复现变异及行为/字节/检索指标。
3. S22/S23：`judge.py` 独立风险审计、人工校准、baseline/消融与可重算报告。
4. S24/S25：`batch_runner.py` 正常并发，然后独立验收 worker 崩溃恢复。

上面文件都待新增；现有探针/检索 eval 是可复用证据，不是完整 Agent 评测器。

最小 manifest 字段固定为 case_id、source_revision、engine_version、visible_project、private_truth、expected_checks、seed。verifier 读取最终磁盘并独立重跑所需引擎/行为检查，不能信任 Agent 写出的 report.status。先输出 PASS/FAIL/INVALID/INCOMPLETE 及逐项证据；环境不可用是 INVALID，单列且不计模型失败；Agent 流程未完成造成的 INCOMPLETE 不算成功，仍保留在有效试验分母，不能靠排除困难样本抬高修复率。至少用一例“报告自称 CLEAN 但文件仍坏”验证它不会被骗。

## 样本与评分

先用 `godot_test/probe_tests/fixtures/phase1/CleanControl` 作为健康候选，在锁定引擎重新验收；不要引用不存在的 clean-control-4x。每个样本含来源 commit/引擎/规则指纹、算子与 seed、可见项目目录和工作区外真值路径。

变异先做 class/注解等窄语法，接着做有上下文约束的 await/connect/method；FileAccess→File.new 不能当通用一行反转。每例先确认健康原版、变异造成目标差异、L0 后是否仍有残余。规则 ID 从真实库读取，例如 `official_renames:4.0:_:class:KinematicBody2D`。

字节 Exact Match 按字节，不能删除字符串空白或缩进；独立行为断言接受等价修复。分别报告 L0-only 与 Agent 修复贡献、未调用检索与 Recall 未命中；调参/测试按来源仓库或规则族隔离。

## Judge

输出包含 SAFE_BY_JUDGE/SUSPICIOUS/FAKE_FIX/INSUFFICIENT_EVIDENCE/JUDGE_ERROR、理由/具体位置及失败类型。SAFE_BY_JUDGE 仅代表未发现风险，不代表语义被证明。输入提供原始/最终函数、必要场景/调用上下文与引用规则；将项目内容作为不可信数据，不执行其中的指令。

人工校准先覆盖删除逻辑、pass stub、异步顺序、信号参数、幻觉 API 与合法重构。报告误放/误杀/分歧；Judge 故障单列为基础设施，不能算语义修复失败。

## 批处理

每仓独立 source/output/run_id；相同名字不能作为唯一键。每 worker 启动后新建句柄；所有 converter/V1/V2/V3/sweep 使用同一 Godot 限流边界。父进程跟踪子进程组与任务，崩溃后清理进程、核对槽位和 resume，再重排；不要假设 Manager semaphore 自动归还。

## 评分进入 Langfuse/Phoenix 的顺序

S01 先固定 case/run/trace 与评分结构；S14 验证 OTel 接线；S21 用版本化 SDK/API 关联 dataset/experiment/score；S22 加 Judge 与人工标注；S23 才据此做对比。OTLP 本身不会自动创建这些评分对象。

评分由独立验证器本地计算并保存，一份结果幂等同步两端；Agent 只看可见输入，不读取真值。程序结果、Judge 和人工意见分别命名且保留版本。新增 backend adapter 与 outbox 的“已接受未响应”测试，避免补传重复；评测全采样，本地/平台指标分母一致。批处理子进程显式传播 W3C 上下文，恢复创建关联的新 trace。详见 [观测契约](../trace/LANDMARKS.md#otel-contract)。

## 批处理重启不另造恢复机制

父进程保存任务与 run_id；worker 崩溃后清理残留进程/槽位，重新调度原 run，新 worker 自建原生 SqliteSaver 与运行句柄，持锁后调用同一 resume 入口。新 OTel trace 不改变 thread_id。checkpoint 只恢复图，工作区互斥、任务监督和外部副作用去重分别验收，见 [恢复契约](../orchestrator/LANDMARKS.md#checkpoint-contract)。

## 本目录执行清单

<a id="s01"></a>

### S01：先建最小独立评测器与观测契约测试

- [ ] 完成 [S01](../../LANDMARKS.md#s01) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：先定义固定 case、隐藏真值、结果分类与独立验证器；同时写 OTel span/评分字段契约和内存 exporter 反例。六类项目先用 fake verifier，再补锁定引擎集成验证。

**交付物**：交付正确/错误/等价替代对照，隐藏答案位于 Agent 工作区外。定义 case_id→run_id→trace/span 的关联及评分明细格式，OTel 正式接线在 S14。

**验收**：错误不通过、缺证据标 INVALID/INCOMPLETE；read/grep 不读真值；fake 调用树与评分重复提交测试先固定预期。

**问题详情与复现**：[EVAL-01 · 参考答案放进项目副本会泄漏给 Agent](DEFECTS.md#eval-01)。

<a id="s21"></a>

### S21：扩展变异、复验 RAG 并接入平台实验

- [ ] 完成 [S21](../../LANDMARKS.md#s21) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：逐例验证健康原版、变异生效和 L0 后残留；独立复验 RAG。新增 Langfuse/Phoenix 的 dataset/experiment/score 适配，评分先本地落盘再幂等推送。

**交付物**：交付可复现样本与逐项结果、两后端对象映射和 outbox。每个 case 关联 run/trace、规则/配置/评测器指纹；同一评分复用，两端不重复跑模型。

**验收**：等价解/行为/字节分开；fresh/reused 和调参/测试隔离；上传断网/重复/响应丢失不重复逻辑评分，两端汇总可由本地明细复算。

**问题详情与复现**：[EVAL-02 · 逐字参考不等于唯一正确解，变异也可能没有测到 Agent](DEFECTS.md#eval-02)；[EVAL-04 · 平台评分没有来源与幂等关联，会重复计分或混用实验](DEFECTS.md#eval-04)。

<a id="s22"></a>

### S22：实现独立 Judge、人工校准与关联标注

- [ ] 完成 [S22](../../LANDMARKS.md#s22) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：程序结果确定事实后，独立 Judge 审语义风险；原始/最终上下文齐全，缺证据与 Judge 故障分流。Judge 调用走 OTel，结果和人工标注关联原 patch/trace/span。

**交付物**：交付结构化 verdict 和校准样本；人工/程序/Judge 分开命名、版本化，一份结果同步两平台，审最终净 diff 及保留 patch。

**验收**：好/坏/存疑/缺证据/模型故障对照；人工误放/误杀/分歧可复算，Judge 费用完整入账，两端不重复评判。

**问题详情与复现**：[EVAL-03 · Judge 的证据不足与调用失败没有独立出口](DEFECTS.md#eval-03)。

<a id="s23"></a>

### S23：完成平台对比实验、baseline 与消融报告

- [ ] 完成 [S23](../../LANDMARKS.md#s23) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：冻结条件后比较有/无 RAG、有/无 L0、rule-only 和通用 coding agent；每条件独立 run_id。Langfuse/Phoenix 关联同一实验清单、trace 与评分，多次试验记录方差。

**交付物**：交付修复率/覆盖/Judge 风险、成本/耗时、人工介入和失败归因。报告含本地逐项来源和后端实验链接；初始错误为零的削减率为 N/A。

**验收**：本地与两端分母、指标和版本一致；引擎/Judge/导出故障单列；评测全采样，生产采样数据不当完整统计；真实 token 节省与估算分开。

<a id="s24"></a>

### S24：实现进程池批处理、上下文传播与限流

- [ ] 完成 [S24](../../LANDMARKS.md#s24) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：每 worker 启动后新建模型/SQLite/Lance 和 OTel provider/exporter；任务信封注入/提取 W3C traceparent/tracestate。所有 converter/V1/V2/V3/sweep 经同一 Godot 槽位边界。 每 run 独立 checkpoint 文件，worker 重开 SqliteSaver；同一 thread_id 不允许并发恢复。

**交付物**：交付 batch CLI、独立运行目录、跨进程关联和正常吞吐数据；正常退出有界 flush/shutdown，不继承活跃导出线程。

**验收**：1/2/4 worker 结果一致、同名不冲突、进程峰值受限；子进程 span 关联正确且不重复埋点，后端故障不打满 worker；单仓失败不抹掉其余结果。

**问题详情与复现**：[BATCH-01 · 杀掉 worker 后槽位与 Godot 子进程未必自动回收](DEFECTS.md#batch-01)。

<a id="s25"></a>

### S25：验收崩溃恢复、观测降级并完成清理

- [ ] 完成 [S25](../../LANDMARKS.md#s25) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：父进程监督并回收残留进程/槽位，按 S19 对账重排；标记中断 trace，以新 trace 关联恢复。清理旧占位、README/ARCHITECTURE/NEXT_STEP 与失效链接。 重新调度保留原 run_id/thread_id，调用同一 resume 入口，不重建初始图输入。

**交付物**：交付 kill/断网/后端不可用测试、恢复及评分补传说明；清单对应真实证据。后端持久化/保留策略按选定部署说明，不承诺超出本地账本的可靠性。

**验收**：无进程/槽位泄漏，任务不丢、受控补丁不重复，未知模型结果单列；导出有界，评分重试不重复；本地与后端差异可解释；真实引擎/后端验收与模拟测试分别报告。

## 完成一项怎么记

在相关 DEFECTS 条目附测试名称/命令、实际结果与版本；只勾本步验收通过的项目。涉及代码的目录同步 README。L3 草稿放本地 DESIGN_NOTES；跨模块有后果的决定落 docs/adr。文档修订完成不等于业务修复完成。
