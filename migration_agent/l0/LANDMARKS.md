# 确定性预处理：实现路标

[全项目执行顺序](../../LANDMARKS.md) · [全项目问题总账](../../DEFECTS.md) · [上级文档](../LANDMARKS.md) · [本级问题](../l0/DEFECTS.md)

更新：2026-10-17。以当前代码为现状；下文未勾选项均为待修复/待开发。**按根目录 S00→S25 执行，到本目录时再展开；本级编号不重新从 1 开始。**

## 文件与执行顺序

待新增 `intake.py/codemod.py/trap_scan.py`。推荐 `run_l0_pipeline(source_repo, target_workspace, config, run_context)` 返回来源/L0 完成 SHA、转换状态、替换/跳过清单、冻结标记、初始诊断与日志引用。

1. 检查目标为空、输入支持范围、引擎版本；目前 verifier 拒收 C#/GDExtension 工程，不能等模型修到一半才告知。
2. 复制源码，排除旧 `.git/.godot/.import/.codeindex`、锁和上次运行产物。必要 ignore 在首提交前确定；状态和报告默认在项目外。
3. 形成原始来源提交；识别支持的 config_version（Godot 3 常见为 4，Godot 4 为 5），其他版本明确拒绝/需人工。已是 4.x 可跳官方转换，但不跳后续残余验证。
4. 受控运行 --convert-3to4，使用独立进程组、超时和日志；这是新 converter 执行器，现有 runner 只支持 V1/V2/V3。非零/超时按结果分类，停止部分转换，不擅自继续。
5. 受控暂存新增/删除/修改并提交；空修改不强行 commit。S16 插入小白名单 codemod 后，再做约定的 UID 规范化与首次 V3。
6. 形成 **B0=L0 完成提交**，不是原始 3.x 提交；所有 Agent revert 不得越过 B0。全量索引后冻结场景一次，保存 commit/规则指纹。

## codemod 的最小安全域

只读真实 migration_rules，筛 `change=rename`、`agent_action=apply_rename`、版本适用、无语义风险的候选；confidence 是标签。初版 .gd 只处理已证明的引擎类型位置；局部遮蔽、未知 receiver、多跳冲突和坏 AST 跳过。

场景 type 槽位覆盖 node/gd_resource/sub_resource/ext_resource；不要全局替换字符串。span 在 UTF-8 bytes 上处理；大于当前写通道 4MB 上限的文件先标需人工，不绕过守卫承诺“全修”。

启动期允许 L0 自己的受控批量事务，保存 dry-run/规则/patch 证据；循环期 targeted codemod 必须经 edit。`.instance()` 的真实规则为 apply_and_warn，不能当无条件安全映射。

## 陷阱结果要能结案

StaticTrapFinding 至少有 rule_id、版本、相对路径、行/片段、严重度、证据、建议与 OPEN/RESOLVED/DISMISSED/NEEDS_HUMAN。扫描 yield/setget/Tween/connect 残余、shader 确定不兼容点，以及按类型确定的 extents 尺寸语义；合法关键词不作裸词黑名单。修后重扫，疑似项可澄清，不要求靠修改正确代码让列表归零。

## 本目录执行清单

<a id="s15"></a>

### S15：实现隔离 intake 与 L0 事务边界

- [ ] 完成 [S15](../../LANDMARKS.md) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：受控复制项目、原始提交、转换、UID/首次导入，形成 L0 完成提交；刷新索引并冻结一次。

**交付物**：交付 run_l0_pipeline 初版及超时/不支持类型/已有目标的明确出口；转换执行器单独封装，不引用不存在的 run_subprocess。

**验收**：源不变、转换新增文件入提交、缓存不弄脏树、失败不标完成、二次启动非 resume 被拒。

**问题详情与复现**：[L0-03 · 接管工作区会带脏产物，转换提交还可能漏新增文件](../l0/DEFECTS.md)。

<a id="s16"></a>

### S16：增加小白名单 codemod 和可结案陷阱扫描

- [ ] 完成 [S16](../../LANDMARKS.md) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：从真实规则筛候选，证明归属后才修改；扫描静默语义风险并支持复扫/确认/排除。循环期确定性替换也走唯一写工具。

**交付物**：交付 dry-run 清单、逐规则替换证据与 StaticTrapFinding；初版超大/未解析文件升级人工，不承诺机械修完。

**验收**：安全改名正例加同名用户符号反例；场景四类 type 槽位；合法 shader 不误报；无修改算子不计收益。

**问题详情与复现**：[L0-01 · 把文字置信标签按数值筛选，选中了错误规则](../l0/DEFECTS.md)；[L0-02 · AST 找到同名节点，不代表它属于引擎 API](../l0/DEFECTS.md)；[L0-04 · 静态陷阱误报合法语法，且没有消项机制](../l0/DEFECTS.md)。

## 完成一项怎么记

在相关 DEFECTS 条目附测试名称/命令、实际结果与版本；只勾本步验收通过的项目。涉及代码的目录同步 README。L3 草稿放本地 DESIGN_NOTES；跨模块有后果的决定落 docs/adr。文档修订完成不等于业务修复完成。
