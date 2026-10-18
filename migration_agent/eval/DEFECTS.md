# 独立评测与批处理：问题与复现

[全项目执行顺序](../../LANDMARKS.md) · [全项目问题总账](../../DEFECTS.md) · [上级文档](../DEFECTS.md) · [本级路标](LANDMARKS.md)

按执行顺序排列。**已复现/源码确认**指已有代码证据；**规划风险**指组件尚未实现，复现描述是先要写下的失败测试。所有代码修复仍未完成，不能把新文档当作修复结果。

## 本级负责的问题

复现均在临时项目/数据库执行；需要 Git 时先提交干净来源，注入成功 sync；需要引擎的条目先完成 S00。源码链接用于定位，精确函数名写在正文，避免依赖易漂移行号。

<a id="eval-01"></a>

### EVAL-01：参考答案放进项目副本会泄漏给 Agent

**顺序 / 状态**：[S01](../../LANDMARKS.md#s01)；规划风险；模块未实现。

**范围与原因**：read/grep 能读取工作区文件。旧方案将包含完整 original_4x_content 的 ground_truth.json 放进 sample 项目，相当于把答案交给被测 Agent。

**具体表现**：模型搜索原报错符号时，直接在 ground_truth.json 里找到健康文件，无需完成迁移推理。

**如何复现**：构造临时 sample，放入带原始代码的 ground_truth.json；调用现有 read 或 grep，确认它可被读取。此为设计反例，不是已存在的评测运行。

**修复办法**：Agent 工作区只含变异项目；答案、行为断言和参考补丁放到工作区外的评测目录。评测前检查读工具、索引和检索输入均不带隐藏真值。

- [ ] **验收测试**：先写真值隔离测试：合法项目文件可读，工作区外答案不可读；准备已知正确、已知错误和等价替代结果三个对照。

**关键源码**：[__init__.py](../../inline_tools/read/__init__.py)、[__init__.py](../../inline_tools/grep/__init__.py)。

<a id="eval-02"></a>

### EVAL-02：逐字参考不等于唯一正确解，变异也可能没有测到 Agent

**顺序 / 状态**：[S21](../../LANDMARKS.md#s21)；规划风险；评分器待实现。

**范围与原因**：等价实现不必复原同一文本；忽略空白会破坏 GDScript 缩进和字符串。若变异在 L0 就被修好，不能算 Agent 修复能力。

**具体表现**：“a b”与“ab”去空白后相等但语义不同；两种等价 await 写法又可能被 Exact Match 拒绝。

**如何复现**：评分器先输入三对样本：字节一致、等价不同文本、字符串/缩进被破坏；另让官方转换器修掉一个简单 rename，检查归因是否仍给 Agent。

**修复办法**：分开字节匹配、独立行为断言、L0 收益、残余 Agent 收益和 Judge 风险。变异记录种子、来源 commit、适用 AST 和真实 rule_id；按来源仓库/规则族划分调参和测试集。

- [ ] **验收测试**：等价替代被行为测试接受；错误字符串/缩进失败；L0-only 单独统计；不适用算子无修改不得生成有效样本。

**关键源码**：[groundtruth.jsonl](../../rag/eval/test_tier_a/groundtruth.jsonl)、[rules.db](../../rag/artifacts/rules.db)、[project.godot](../../godot_test/probe_tests/fixtures/phase1/CleanControl/project.godot)。

<a id="eval-04"></a>

### EVAL-04：平台评分没有来源与幂等关联，会重复计分或混用实验

**顺序 / 状态**：[S21](../../LANDMARKS.md#s21)；新增规划风险；评测适配器尚未实现。

**范围与原因**：OTLP 导出 trace 不等于创建数据集、实验和评分。Langfuse 与 Phoenix 各有评分/实验接口，必须关联相同 case、配置、规则版本、trace/span 和评测器版本；两边独立跑 Judge 还会重复付费。

**具体表现**：同一 case 上传超时后重试，后台出现两个得分；或无 RAG 实验的评分错挂到有 RAG trace，最终对比无法复算。

**如何复现**：先用假后端：评分已接收但响应丢失，随后重试同一 item；断言只有一个逻辑评分。再给同一 case 两种配置，确认不会共享实验条目；检查未调用第二次 Judge。当前没有这些适配器，应从失败测试开始。

**修复办法**：评分先写本地明细和 export_outbox，再通过版本锁定的 SDK/API 发送。幂等键包含 backend、experiment_run_id、item_id、metric 和 evaluator_version；保存平台对象 ID 便于查询后重试。同一独立评分结果映射到两端，不重新评判。

- [ ] **验收测试**：断网重试、已接受未响应、重复提交、版本变化、双后端任一失败均有测试；本地汇总与平台逐项对齐。隐藏真值只供隔离评测器，默认不随 trace 上传。

**关键源码**：[__init__.py](__init__.py)、[__init__.py](../trace/__init__.py)、[run_eval.py](../../rag/eval/run_eval.py)。

<a id="eval-03"></a>

### EVAL-03：Judge 的证据不足与调用失败没有独立出口

**顺序 / 状态**：[S22](../../LANDMARKS.md#s22)；规划风险；Judge 待实现。

**范围与原因**：旧 verdict 只有安全/可疑/假修复。diff 不能证明所有调用语义；模型超时也不是代码语义坏。

**具体表现**：没有场景信号上下文时看不出回调参数丢失；Judge 超时却被当作 FAKE_FIX 会低估修复率。

**如何复现**：准备保留信号/破坏信号的两份 diff，分别提供和移除场景上下文；另让 Judge 桩超时或返回坏 JSON，检查旧三态是否只能误分类。

**修复办法**：先程序化事实检查，再独立 Judge。增加 INSUFFICIENT_EVIDENCE/JUDGE_ERROR，提供必要原始/最终上下文与引用规则，忽略项目文本中的指令。人工校准误放/误杀与分歧。

- [ ] **验收测试**：真修、假修、存疑、证据缺失、超时、坏结构都有测试；Judge 未发现风险不得对外写成语义已证明。

**关键源码**：[__init__.py](__init__.py)、[guard.py](../../inline_tools/editandfixguard/guard.py)。

<a id="batch-01"></a>

### BATCH-01：杀掉 worker 后槽位与 Godot 子进程未必自动回收

**顺序 / 状态**：[S24](../../LANDMARKS.md#s24)；规划风险；批处理待实现。

**范围与原因**：Manager semaphore 是计数，worker 死亡不会自动补回；Godot 另建 session，父 worker 死后仍可能运行。已有 verify/daemon 锁也不是整次迁移锁。

**具体表现**：两槽中一个 worker 持槽被 kill -9，后续任务永远少一个槽；残留 Godot 继续占内存。

**如何复现**：先用受控假 Godot 长进程，worker 取槽后通知父进程，再由父进程杀 worker；检查剩余子进程、可用槽数和待处理任务。不得对个人工作进程随意 kill。

**修复办法**：父进程监督 worker/子进程组并持久化任务与 run_id；清理残留进程、重建可验证的槽位/池后，重新取得工作区锁。新 worker 重开原 run 的 SqliteSaver/审计连接，用同一 thread_id 对账后恢复。checkpoint 不负责杀进程、归还信号量或重新调度任务。

- [ ] **验收测试**：正常 1/2/4 worker 结果一致；受控崩溃后无残留进程或槽位泄漏，同一 run 不并发接管；新 worker 从原 checkpoint 恢复，受控补丁无重复副作用，未知外部调用费用有单独状态。

**关键源码**：[runner.py](../../codebase_index/godot_mcp/src/godot_mcp/verify/runner.py)、[lock.py](../../codebase_index/godot_mcp/src/godot_mcp/verify_shell/lock.py)。
