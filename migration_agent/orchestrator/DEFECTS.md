# 单仓编排：问题与复现

[全项目执行顺序](../../LANDMARKS.md) · [全项目问题总账](../../DEFECTS.md) · [上级文档](../DEFECTS.md) · [本级路标](LANDMARKS.md)

按执行顺序排列。**已复现/源码确认**指已有代码证据；**规划风险**指组件尚未实现，复现描述是先要写下的失败测试。所有代码修复仍未完成，不能把新文档当作修复结果。

## 本级负责的问题

复现均在临时项目/数据库执行；需要 Git 时先提交干净来源，注入成功 sync；需要引擎的条目先完成 S00。源码链接用于定位，精确函数名写在正文，避免依赖易漂移行号。

<a id="orc-01"></a>

### ORC-01：宿主若照旧签名封装，工具无法完成一次调用

**顺序 / 状态**：[S14](../../LANDMARKS.md#s14)；规划契约已纠正；适配器待实现。

**范围与原因**：编排包目前只有骨架。旧方案用 read_file/edit_file/execute_verify_shell 及 PASS 等不存在的底层接口。

**具体表现**：编辑返回 ok/commit，宿主却等 status=COMMITTED，于是漏记补丁；Gate 从不返回 UPGRADE_MODEL_TIER。

**如何复现**：先写适配器契约测试，用真实 edit 返回字典和 VerifyGateResult 驱动旧字段读取；这会失败，属于待实现适配器的反例。

**修复办法**：固定宿主工具名与底层真实函数映射；升级/回滚由宿主明确推导。禁止自由 Bash/argv，路径和数据库由闭包注入，模型不能替换。

- [ ] **验收测试**：不接 LLM，先逐个调用七个工具；断言 schema、路径隔离、错误返回和提交登记；用程序化桩驱动一轮。

**关键源码**：[__init__.py](../../inline_tools/read/__init__.py)、[__init__.py](../../inline_tools/grep/__init__.py)、[edit.py](../../inline_tools/editandfixguard/edit.py)、[models.py](../../codebase_index/godot_mcp/src/godot_mcp/verify_gate/models.py)。

<a id="orc-03"></a>

### ORC-03：动态资源扫描带 check-only，循环不会执行

**顺序 / 状态**：[S17](../../LANDMARKS.md#s17)；命令语义已核对；扫描器待实现。

**范围与原因**：V1 已用哨兵 preload 全库 .gd；补充 sweep 负责剩余资源。旧命令带 --check-only，只解析扫描脚本，不运行动态 load。

**具体表现**：扫描脚本的 _initialize 中打印 SCAN_DONE 并加载坏场景；旧命令可能既没打印也没发现坏场景。

**如何复现**：需目标 Godot：临时完整项目写带 SCAN_BEGIN/SCAN_DONE 的 SceneTree 脚本，分别带/不带 --check-only 执行；旧命令缺少运行哨兵。当前机器无引擎，属于待引擎集成复现。

**修复办法**：保留 V1/V2/V3，新增固定受控 sweep 模式，移除 check-only，由脚本 quit。逐资源记录开始/完成、完整清单、超时/崩溃未检查集合；不能靠退出码 0 宣布扫完。

- [ ] **验收测试**：未挂载坏场景检出、干净对照通过、漏 DONE/超时/崩溃标不完整；load 成功不代表实例化或渲染行为正确。

**关键源码**：[sentinel.py](../../codebase_index/godot_mcp/src/godot_mcp/verify/sentinel.py)、[commands.py](../../codebase_index/godot_mcp/src/godot_mcp/verify/commands.py)、[runner.py](../../codebase_index/godot_mcp/src/godot_mcp/verify/runner.py)。

<a id="orc-02"></a>

### ORC-02：根因为空或 CLEAN 不等于验证完整

**顺序 / 状态**：[S17](../../LANDMARKS.md#s17)；底层状态已复现；宿主成功门待实现。

**范围与原因**：filter 允许没有根因却有 pending pointer/untrusted。场景检查也有弃权、跳过和历史问题。只看状态会签发假成功。

**具体表现**：project_status=CLEAN，但 probe_incomplete=True、gdscript_complete=False；场景 pre_existing 也仍是未解决错误。

**如何复现**：用 make_view(pointers=("P",)) 构造 Gate 请求并 evaluate，打印四个字段；再构造有 untrusted_files 的 merge 结果。

**修复办法**：统一成功谓词，同时检查健康、非硬停止、脚本覆盖、无未解 pointer、要求的资源验证、场景与陷阱结案。不完整输出 PARTIAL/ESCALATED；报告保留各验证维度。

- [ ] **验收测试**：好/坏/证据不足矩阵逐项翻转；跳过、弃权、不可信和未完成 sweep 都不得输出完整 CLEAN。

**关键源码**：[merge.py](../../codebase_index/godot_mcp/src/godot_mcp/verify_filter/merge.py)、[models.py](../../codebase_index/godot_mcp/src/godot_mcp/verify_gate/models.py)、[check.py](../../codebase_index/index/src/codeindex/scene/check.py)。

<a id="orc-04"></a>

### ORC-04：新增诊断就回滚，会把真正进展当作恶化

**顺序 / 状态**：[S18](../../LANDMARKS.md#s18)；规划风险；宿主策略待实现。

**范围与原因**：编译错误会遮挡后续错误。修复 A 后首次看到 B，不一定是新补丁造成；一次提交多个补丁时“上一 patch”也不等于整轮候选。

**具体表现**：语法错误 A 修好，原来就存在的类型错误 B 被暴露；机械比较签名集合会将正确补丁回滚。

**如何复现**：先用假 verifier 返回 A→B，标注 B 在未修改位置；再构造候选补丁引入真正新错误 C。旧“new_signatures 非空即回滚”对两者作同样判断。

**修复办法**：区分已证明回归、诊断暴露和未知变化；看修改范围、诊断位置与覆盖，无法证明时保守复核或升级。保存 round_start_sha 和候选 patch 列表，整组回滚后重同步并验证。

- [ ] **验收测试**：A→B 正常继续、引入 C 回滚、未知变化退出有原因；真正循环/无进展有界停止，不在确定性回滚后制造假震荡。

**关键源码**：[models.py](../../codebase_index/godot_mcp/src/godot_mcp/verify_gate/models.py)、[git_txn.py](../../inline_tools/editandfixguard/git_txn.py)。

<a id="orc-05"></a>

### ORC-05：图状态恢复未指定原生 checkpointer，容易与审计账本重复实现

**顺序 / 状态**：[S18](../../LANDMARKS.md#s18)；规划遗漏已纠正；checkpointer 尚未接入。

**范围与原因**：编排目前只有包骨架；原规划描述 graph/state 和 SQLite 恢复，却未指定持久化 checkpointer、thread_id 或恢复入口。现有 Gate InMemoryStateStore 在进程退出后清空，OTel 也不能替代图状态。

**具体表现**：模型已经生成补丁提案后退出，重新建图若未配置持久化 checkpointer，就无法读取原目标、消息和下一节点；只查 round 记录也不能还原 LangGraph 调度状态。

**如何复现**：S18 新增双进程契约测试：进程 A 用假模型生成提案并持久化，再在 apply 前故障退出；进程 B 新建 SqliteSaver 和同一版本图，以原 thread_id 读取 state 并继续。未接 checkpointer 或换成 InMemorySaver 时应失败。

**修复办法**：执行本级 checkpoint-contract：S18 使用原生 SqliteSaver 和 durability="sync"，thread_id 固定等于 run_id；图状态只由 checkpoint 恢复，SQLite 审计表不自建下一节点调度器。S19 再补外部副作用对账。

- [ ] **验收测试**：全新进程可恢复提案/目标/完整 Gate 状态；新 run 隔离，原 run 恢复保持 thread_id；已完成 run 不重启；序列化不包含连接、锁或 tracer；节点失败与进程 kill 分别测试。

**关键源码**：[__init__.py](__init__.py)、[__init__.py](../trace/__init__.py)、[state_store.py](../../codebase_index/godot_mcp/src/godot_mcp/verify_gate/state_store.py)。
