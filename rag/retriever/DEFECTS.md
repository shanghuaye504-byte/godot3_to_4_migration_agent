# 检索运行时：问题与复现

[全项目执行顺序](../../LANDMARKS.md) · [全项目问题总账](../../DEFECTS.md) · [上级文档](../DEFECTS.md) · [本级路标](LANDMARKS.md)

按执行顺序排列。**已复现/源码确认**指已有代码证据；**规划风险**指组件尚未实现，复现描述是先要写下的失败测试。所有代码修复仍未完成，不能把新文档当作修复结果。

## 本级负责的问题

复现均在临时项目/数据库执行；需要 Git 时先提交干净来源，注入成功 sync；需要引擎的条目先完成 S00。源码链接用于定位，精确函数名写在正文，避免依赖易漂移行号。

<a id="rag-02"></a>

### RAG-02：错误配置键被忽略，调参看似成功实则未生效

**顺序 / 状态**：[S13](../../LANDMARKS.md#s13)；已复现；配置校验待修。

**范围与原因**：现有开关是 channels，rrf_k 位于 fusion；Pydantic 默认忽略额外字段。旧文档的 enabled 和顶层 rrf_k 不生效。

**具体表现**：把 tier_b.rrf_k 设为 17，实际 config.tier_b.fusion.rrf_k 仍是 60。

**如何复现**：RetrieverConfig.model_validate({"tier_b":{"rrf_k":17,"bm25":{"enabled":False}}}) 后打印 model_dump，检查实际值。

**修复办法**：配置模型拒绝未知键；YAML 用 channels 与 fusion.rrf_k。20/20、0.3/0.7 是待复验候选，独立测试集比较通过再更新默认值。

- [ ] **验收测试**：未知键、嵌套错位、合法三种 channels 都有测试；测试业务约束，不只硬编码旧默认值。

**关键源码**：[config.py](config.py)、[retriever.yaml](retriever.yaml)。

<a id="rag-03"></a>

### RAG-03：报错符号提取不足，精确检索被跳过

**顺序 / 状态**：[S13](../../LANDMARKS.md#s13)；源码确认；代码待修。

**范围与原因**：未显式提供 symbols 时，router 只识别四种句式。其他常见类型/属性/函数报错会提取不到符号。

**具体表现**：Invalid set index 与 Function "instance" not found 不命中已有 get-index/Nonexistent-function 正则。

**如何复现**：分别把上述句式及 Cannot find member "foo" in base "Bar" 传给 extract_symbols，检查列表。

**修复办法**：扩展从真实日志提取的有边界句式；保留引号差异和去重。宿主已有 ClassifiedEvent.symbol 时优先显式传入，并带 owner 上下文而非仅靠 regex。

- [ ] **验收测试**：每种新句式一个正例和无关文本反例；额外 owner 不得误当待改方法。

**关键源码**：[router.py](router.py)、[test_retriever_router.py](../test/test_retriever_router.py)。

<a id="rag-06"></a>

### RAG-06：缓存命中不触发观测钩子，调用账本少一段

**顺序 / 状态**：[S13](../../LANDMARKS.md#s13)；源码确认；整合待修。

**范围与原因**：retrieve_cached 命中后直接返回，observer 看不到这次调用。仅靠 observer 统计检索次数会低估缓存命中和调用总量。

**具体表现**：相同查询调用两次，第二次 cache_hit=True，却只有第一次产生 retrieve-end。

**如何复现**：用记录事件的 observer 调两次 retrieve_cached，比较返回 cache_hit 和事件数；测试可用注入句柄避免下载模型。

**修复办法**：宿主每次工具调用都记账；库命中分支也明确发出带 request_id 的缓存事件或 end 事件，避免宿主/库重复计次。

- [ ] **验收测试**：两次调用两个 call_id、一次真实检索、一次缓存命中；observer 失败不阻断业务，但审计落账失败要显式报告。

**关键源码**：[cache.py](cache.py)、[observe.py](observe.py)。
