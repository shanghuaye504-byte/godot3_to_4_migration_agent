# 确定性预处理：问题与复现

[全项目执行顺序](../../LANDMARKS.md) · [全项目问题总账](../../DEFECTS.md) · [上级文档](../DEFECTS.md) · [本级路标](LANDMARKS.md)

按执行顺序排列。**已复现/源码确认**指已有代码证据；**规划风险**指组件尚未实现，复现描述是先要写下的失败测试。所有代码修复仍未完成，不能把新文档当作修复结果。

## 本级负责的问题

复现均在临时项目/数据库执行；需要 Git 时先提交干净来源，注入成功 sync；需要引擎的条目先完成 S00。源码链接用于定位，精确函数名写在正文，避免依赖易漂移行号。

<a id="l0-03"></a>

### L0-03：接管工作区会带脏产物，转换提交还可能漏新增文件

**顺序 / 状态**：[S15](../../LANDMARKS.md#s15)；已复现的组合问题；intake 待实现。

**范围与原因**：edit 要求干净 Git 树。旧 intake 忽略了 trace/锁/索引等产物，又用 commit -am 保存转换，无法纳入新增文件。

**具体表现**：仅创建未忽略 .migration_trace.db，下一次编辑就 DIRTY_WORKTREE；转换生成新 .gdshader 时 -am 不提交它。

**如何复现**：临时 Git 仓库创建 trace 文件后调用 precheck；另新增 shader 并执行 commit -am，检查 git status。均只在临时副本操作。

**修复办法**：新目标为空才接管；排除旧运行产物，trace/report 置于受管状态目录；必要 ignore 在首提交前写好。源提交、转换提交、L0 完成提交分开，使用受控 add -A，超时停止而不假装完成。

- [ ] **验收测试**：源目录不变；新增/删除文件均入账；已有目标拒绝；超时不生成成功 B0；UID/V3 后工作树干净且基线只冻结一次。

**关键源码**：[precheck.py](../../inline_tools/editandfixguard/precheck.py)、[git_txn.py](../../inline_tools/editandfixguard/git_txn.py)、[runner.py](../../codebase_index/godot_mcp/src/godot_mcp/verify/runner.py)。

<a id="l0-01"></a>

### L0-01：把文字置信标签按数值筛选，选中了错误规则

**顺序 / 状态**：[S16](../../LANDMARKS.md#s16)；真实库查询已复现；codemod 待实现。

**范围与原因**：confidence 是 TEXT，绝大多数规则为 NULL；数值比较不是“可信度至少 90%”。唯一映射也不自动代表可以安全改。

**具体表现**：class AND confidence>=0.9 实际返回 3 条 needs_review 的 behavior，而非 198 条候选 apply_rename 类规则。

**如何复现**：只读执行 SELECT old_symbol,confidence,change FROM migration_rules WHERE symbol_kind='class' AND confidence>=0.9，对比 change=rename、agent_action=apply_rename 的结果。

**修复办法**：按 change、agent_action、版本窗口和语义风险筛选；confidence 按枚举处理。规则 ID 来自库，冲突/多跳要解析；apply_and_warn 不纳入无条件自动替换。

- [ ] **验收测试**：固定真实库抽样集，确认 needs_review/behavior 不被当作安全改名；版本不适用、冲突链及 do_not_fix 都被跳过并有原因。

**关键源码**：[rules.db](../../rag/artifacts/rules.db)、[schemas.py](../../rag/retriever/schemas.py)。

<a id="l0-02"></a>

### L0-02：AST 找到同名节点，不代表它属于引擎 API

**顺序 / 状态**：[S16](../../LANDMARKS.md#s16)；规划风险；codemod 待实现。

**范围与原因**：AST 能避开注释，却不能仅凭 identifier 名字区分局部变量与引擎类型；唯一 old→new 也不能证明 receiver 类型。场景方案还漏资源头和 sub_resource。

**具体表现**：用户局部变量 Spatial 被改成 Node3D；自定义对象的 instance() 被误改。大于 4MB 文件又被当前写工具拒绝。

**如何复现**：设计反例：准备含同名局部变量、自定义 instance 方法、注释/字符串和四种场景 type 槽位的健康输入，比较拟议替换结果。

**修复办法**：初版只改已证明为引擎类型的少量位置，未知归属跳过；场景覆盖 node/gd_resource/sub_resource/ext_resource。统一 UTF-8 span；>4MB 初版标为需人工，不承诺靠绕过守卫补齐。

- [ ] **验收测试**：每个正例配同名用户符号反例；补丁先 dry-run；循环期所有替换走 edit；未解析和大文件进入报告。

**关键源码**：[gdscript.py](../../codebase_index/index/src/codeindex/parsers/gdscript.py)、[precheck.py](../../inline_tools/editandfixguard/precheck.py)、[model.py](../../codebase_index/index/src/codeindex/scene/model.py)。

<a id="l0-04"></a>

### L0-04：静态陷阱误报合法语法，且没有消项机制

**顺序 / 状态**：[S16](../../LANDMARKS.md#s16)；规划风险；扫描器待实现。

**范围与原因**：合法 shader 标识被列入旧语法示例；pending_traps 又要求全清零，疑似项无法澄清时会卡死。yield/setget 还可能与已有编译诊断重复计数。

**具体表现**：合法 canvas_item 的 TEXTURE_PIXEL_SIZE 或 world_vertex_coords 仅因出现就触发陷阱，Agent 被迫“修”正确代码。

**如何复现**：设计反例：使用合法 CanvasItem shader 与 hint_albedo 旧语法各一例，按旧关键词规则扫描；再保留同一 finding 连续两轮，检查能否退出。

**修复办法**：规则带版本、语法上下文、严重度和证据；确定错误阻塞，疑似项可确认/排除/升级。修复后重扫，和编译诊断按来源关联；按具体 Shape 类型处理 extents 尺寸语义。

- [ ] **验收测试**：合法 shader 不误报；确定旧语法命中；疑似误报可结案；extents 不套统一倍数；缺少目标版本证据时记录待确认。

**关键源码**：[upgrading_to_godot_4.rst](../../rag/artifacts/agent_context/upgrading_to_godot_4.rst)、[schemas.py](../../rag/retriever/schemas.py)。
