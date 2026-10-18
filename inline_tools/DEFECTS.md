# 原生工具：问题与复现

[全项目执行顺序](../LANDMARKS.md) · [全项目问题总账](../DEFECTS.md) · [上级文档](../DEFECTS.md) · [本级路标](../inline_tools/LANDMARKS.md)

按执行顺序排列。**已复现/源码确认**指已有代码证据；**规划风险**指组件尚未实现，复现描述是先要写下的失败测试。所有代码修复仍未完成，不能把新文档当作修复结果。

## 下级导航

- [受控编辑与守卫](editandfixguard/DEFECTS.md)

## 本范围问题索引

- [ ] S06 · [EDT-01 · 包入口没有导出约定的 edit API](editandfixguard/DEFECTS.md)
- [ ] S06 · [EDT-02 · 函数改名后场景仍用旧名，编辑流水线没有提醒](editandfixguard/DEFECTS.md)
- [ ] S06 · [EDT-03 · 索引文件存在就关闭 grep 回退，导致漏报](editandfixguard/DEFECTS.md)
- [ ] S07 · [EDT-04 · 写后复核把存量场景错误当作新回归](editandfixguard/DEFECTS.md)
- [ ] S07 · [EDT-05 · create 绕过语法和反向迁移检查](editandfixguard/DEFECTS.md)
- [ ] S08 · [EDT-06 · 非脚本文件缺通用守卫，场景删除也未覆盖](editandfixguard/DEFECTS.md)
- [ ] S08 · [EDT-07 · G5.1 只看声明名字，既漏旧 API 又误杀用户函数](editandfixguard/DEFECTS.md)
- [ ] S08 · [EDT-08 · git apply 临时补丁文件未清理](editandfixguard/DEFECTS.md)
- [ ] S11 · [EDT-09 · 同步没有绑定当前项目，整轮回滚又只刷新一个文件](editandfixguard/DEFECTS.md)
