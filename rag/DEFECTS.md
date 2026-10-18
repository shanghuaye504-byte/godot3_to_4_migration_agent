# 迁移知识库：问题与复现

[全项目执行顺序](../LANDMARKS.md) · [全项目问题总账](../DEFECTS.md) · [上级文档](../DEFECTS.md) · [本级路标](LANDMARKS.md)

按执行顺序排列。**已复现/源码确认**指已有代码证据；**规划风险**指组件尚未实现，复现描述是先要写下的失败测试。所有代码修复仍未完成，不能把新文档当作修复结果。

## 下级导航

- [知识库构建](build/DEFECTS.md)
- [检索运行时](retriever/DEFECTS.md)
- [检索质量评测](eval/DEFECTS.md)

## 本范围问题索引

- [ ] S12 · [RAG-01 · 散文写入与读取路径不一致，测试靠 skip 避开](build/DEFECTS.md#rag-01)
- [ ] S12 · [RAG-05 · 旧构建和评测命令仍是占位壳](build/DEFECTS.md#rag-05)
- [ ] S13 · [RAG-02 · 错误配置键被忽略，调参看似成功实则未生效](retriever/DEFECTS.md#rag-02)
- [ ] S13 · [RAG-03 · 报错符号提取不足，精确检索被跳过](retriever/DEFECTS.md#rag-03)
- [ ] S13 · [RAG-06 · 缓存命中不触发观测钩子，调用账本少一段](retriever/DEFECTS.md#rag-06)
- [ ] S21 · [RAG-04 · 历史复用和指标命名容易把旧结果说成新实测](eval/DEFECTS.md#rag-04)
