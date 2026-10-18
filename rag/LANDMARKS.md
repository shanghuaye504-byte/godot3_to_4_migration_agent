# 迁移知识库：实现路标

[全项目执行顺序](../LANDMARKS.md) · [全项目问题总账](../DEFECTS.md) · [上级文档](../LANDMARKS.md) · [本级问题](../rag/DEFECTS.md)

更新：2026-10-17。以当前代码为现状；下文未勾选项均为待修复/待开发。**按根目录 S00→S25 执行，到本目录时再展开；本级编号不重新从 1 开始。**

## 当前已具备什么

真实规则库在 `artifacts/rules.db`：上一轮读取 8260 行，目标版本元数据 4.7.1；B 层在 `artifacts/corpora/default/corpus.lance`，上一轮读取 317 行。数量是快照，不写死进业务逻辑。

运行时使用 `rag.retriever` 的 `load/retrieve/retrieve_cached`；build、eval 不进入 Agent 工具依赖路径。S12/S13 修接线，S21 在独立测试集复验配置；不以“98% 完成”代替剩余验收条目。

## 对宿主的约定

每 worker 启动后 `load(artifacts_dir=..., config_path=...)` 一次；不把 SQLite/Lance/嵌入模型句柄跨进程传递。查询必须带 target_version；语料/配置/模型指纹进入 trace。命中结构化规则不代表自动允许修改，还要看 agent_action 和归属。

## 下级导航

- [知识库构建](build/LANDMARKS.md)
- [检索运行时](retriever/LANDMARKS.md)
- [检索质量评测](eval/LANDMARKS.md)

## 本目录执行清单

<a id="s12"></a>

- [ ] **S12 · 修 RAG 输入路径并清理失效入口**：[知识库构建](build/LANDMARKS.md)；先完成根队列的前置步骤，验收看负责目录。

<a id="s13"></a>

- [ ] **S13 · 修检索配置、符号提取和 OTel 观测事件**：[检索运行时](retriever/LANDMARKS.md)；先完成根队列的前置步骤，验收看负责目录。

<a id="s21"></a>

- [ ] **S21 · 扩展变异、复验 RAG 并接入平台实验**：[检索质量评测](eval/LANDMARKS.md)、[检索运行时](retriever/LANDMARKS.md)；先完成根队列的前置步骤，验收看负责目录。

<a id="s25"></a>

### S25：验收崩溃恢复、观测降级并完成清理

- [ ] 完成 [S25](../LANDMARKS.md) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：校正本范围 README/CHECKPOINT 中已实现内容、依赖组和 corpus 路径；保留历史评测来源，不冒充新成绩。

**交付物**：交付可复现的构建/检索/评测使用说明。

**验收**：路径和命令有效，模型缓存与产物要求写清。

## 完成一项怎么记

在相关 DEFECTS 条目附测试名称/命令、实际结果与版本；只勾本步验收通过的项目。涉及代码的目录同步 README。L3 草稿放本地 DESIGN_NOTES；跨模块有后果的决定落 docs/adr。文档修订完成不等于业务修复完成。
