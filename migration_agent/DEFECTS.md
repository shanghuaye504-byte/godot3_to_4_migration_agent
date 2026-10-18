# 宿主与命令行：问题与复现

[全项目执行顺序](../LANDMARKS.md) · [全项目问题总账](../DEFECTS.md) · [上级文档](../DEFECTS.md) · [本级路标](LANDMARKS.md)

按执行顺序排列。**已复现/源码确认**指已有代码证据；**规划风险**指组件尚未实现，复现描述是先要写下的失败测试。所有代码修复仍未完成，不能把新文档当作修复结果。

## 下级导航

- [确定性预处理](l0/DEFECTS.md)
- [单仓编排](orchestrator/DEFECTS.md)
- [轨迹、预算与恢复](trace/DEFECTS.md)
- [独立评测与批处理](eval/DEFECTS.md)

## 本范围问题索引

- [ ] S01 · [EVAL-01 · 参考答案放进项目副本会泄漏给 Agent](eval/DEFECTS.md#eval-01)
- [ ] S14 · [ORC-01 · 宿主若照旧签名封装，工具无法完成一次调用](orchestrator/DEFECTS.md#orc-01)
- [ ] S14 · [TRC-01 · 按 repo_id 保存一行，无法区分试验和多个补丁](trace/DEFECTS.md#trc-01)
- [ ] S14 · [TRC-04 · 只给成功轮次记成本，预算与可观测性不完整](trace/DEFECTS.md#trc-04)
- [ ] S14 · [TRC-05 · 缺少统一调用链，检索、补丁与引擎失败无法关联](trace/DEFECTS.md#trc-05)
- [ ] S15 · [L0-03 · 接管工作区会带脏产物，转换提交还可能漏新增文件](l0/DEFECTS.md#l0-03)
- [ ] S16 · [L0-01 · 把文字置信标签按数值筛选，选中了错误规则](l0/DEFECTS.md#l0-01)
- [ ] S16 · [L0-02 · AST 找到同名节点，不代表它属于引擎 API](l0/DEFECTS.md#l0-02)
- [ ] S16 · [L0-04 · 静态陷阱误报合法语法，且没有消项机制](l0/DEFECTS.md#l0-04)
- [ ] S17 · [ORC-03 · 动态资源扫描带 check-only，循环不会执行](orchestrator/DEFECTS.md#orc-03)
- [ ] S17 · [ORC-02 · 根因为空或 CLEAN 不等于验证完整](orchestrator/DEFECTS.md#orc-02)
- [ ] S18 · [ORC-04 · 新增诊断就回滚，会把真正进展当作恶化](orchestrator/DEFECTS.md#orc-04)
- [ ] S18 · [ORC-05 · 图状态恢复未指定原生 checkpointer，容易与审计账本重复实现](orchestrator/DEFECTS.md#orc-05)
- [ ] S19 · [TRC-02 · Git、副作用账本与图 checkpoint 之间有崩溃窗口](trace/DEFECTS.md#trc-02)
- [ ] S19 · [TRC-06 · 观测导出与恢复混用会丢账，进程切换还会断链](trace/DEFECTS.md#trc-06)
- [ ] S20 · [TRC-03 · 每仓本地缓存不能跨仓复用，短 key 又可能复用错修复](trace/DEFECTS.md#trc-03)
- [ ] S21 · [EVAL-02 · 逐字参考不等于唯一正确解，变异也可能没有测到 Agent](eval/DEFECTS.md#eval-02)
- [ ] S21 · [EVAL-04 · 平台评分没有来源与幂等关联，会重复计分或混用实验](eval/DEFECTS.md#eval-04)
- [ ] S22 · [EVAL-03 · Judge 的证据不足与调用失败没有独立出口](eval/DEFECTS.md#eval-03)
- [ ] S24 · [BATCH-01 · 杀掉 worker 后槽位与 Godot 子进程未必自动回收](eval/DEFECTS.md#batch-01)
