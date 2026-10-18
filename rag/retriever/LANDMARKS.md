# 检索运行时：实现路标

[全项目执行顺序](../../LANDMARKS.md) · [全项目问题总账](../../DEFECTS.md) · [上级文档](../LANDMARKS.md) · [本级问题](DEFECTS.md)

更新：2026-10-17。以当前代码为现状；下文未勾选项均为待修复/待开发。**按根目录 S00→S25 执行，到本目录时再展开；本级编号不重新从 1 开始。**

## 真实契约

`RetrievalQuery(error_text=None, symbols=[], query_text=None, target_version=..., retrieval_mode=..., top_k=..., top_k_a=..., top_k_b=...)`。三种查询输入至少有一种有效；返回 `structured_hits/prose_hits/coverage/recommended_action/cache_hit`，没有 rule_hits/chunk_hits。

Agent 的 top_k 不是唯一截断来源；现有 effective_k_a/effective_k_b 还读 YAML。宿主需明确传 top_k_a/top_k_b，或接受统一配置上限，不能以为工具参数 top_k=5 一定给两层各 5 条。

## 候选配置，不是无条件最优

```yaml
tier_a:
  top_k: 8
tier_b:
  channels: hybrid
  bm25: {k: 20, weight: 0.3}
  vector: {k: 20, weight: 0.7}
  fusion: {method: rrf, rrf_k: 60}
  recall_k: 20
  rerank_k: 3
  score_threshold: null
  reranker: identity
```

S13 校验结构，S21 比较候选与现有默认；独立测试通过再回写生产 YAML。历史 30 条样本支持 identity 的选型，但 0.3:0.7 与等权在不同指标上有取舍。

宿主事件记录每次调用，observer 记录内部检索阶段；两层用同一 request_id/call_id 关联而不重复计数。缓存命中必须有事件。

## RAG 观测边界

本库 observer 输出请求 ID、缓存命中、候选规则/文档 ID、通道/融合/重排耗时及配置/语料指纹；宿主将其转为 OpenInference 兼容的 OTel 子 span，统一送 Langfuse/Phoenix。库不接管全局 provider，不把 GT 放进输入。S13 先补缓存分支事件，S14 接宿主适配器，S21 将逐查询分数挂到对应 span，见 [观测契约](../../migration_agent/trace/LANDMARKS.md#otel-contract)。

## 本目录执行清单

<a id="s13"></a>

### S13：修检索配置、符号提取和 OTel 观测事件

- [ ] 完成 [S13](../../LANDMARKS.md#s13) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：拒绝未知键，使用 fusion.rrf_k/channels，补真实报错句式。统一 observer 的开始/结束/缓存字段，为 S14 的 OTel 适配保留 request/call_id；候选参数留 S21 独立复验。

**交付物**：交付命中/未命中均可关联的检索事件；只记录必要候选 ID、版本、排序与耗时，不将真值送进检索输入。

**验收**：两次调用、一次缓存命中可观测；observer 异常不改变检索结果；宿主与库不重复记账；规则/语料可打开。

**问题详情与复现**：[RAG-02 · 错误配置键被忽略，调参看似成功实则未生效](DEFECTS.md#rag-02)；[RAG-03 · 报错符号提取不足，精确检索被跳过](DEFECTS.md#rag-03)；[RAG-06 · 缓存命中不触发观测钩子，调用账本少一段](DEFECTS.md#rag-06)。

<a id="s21"></a>

### S21：扩展变异、复验 RAG 并接入平台实验

- [ ] 完成 [S21](../../LANDMARKS.md#s21) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：使用 rag/eval 的独立测试结果决定是否采用候选 YAML，保存配置与语料指纹。变异集由 migration_agent/eval 负责。

**交付物**：交付新旧生产候选比较与选定配置，保留取舍理由。

**验收**：新旧配置同集同预算；历史缓存不混入新配置结果。

## 完成一项怎么记

在相关 DEFECTS 条目附测试名称/命令、实际结果与版本；只勾本步验收通过的项目。涉及代码的目录同步 README。L3 草稿放本地 DESIGN_NOTES；跨模块有后果的决定落 docs/adr。文档修订完成不等于业务修复完成。
