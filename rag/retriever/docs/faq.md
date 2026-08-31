# FAQ

**为什么不让调用方直接传一个 filter 字典？**  
灵活性和「LLM 不可能构造出危险查询」是矛盾的。`RetrievalQuery` 每加一个字段都是一次显式设计决策。

**A 层和 B 层的分数能比大小吗？**  
不能。A 层是命中方式置信度（1.0 / 0.7）。B 层是 RRF 上界归一化后的 `[0, 1]`。`merged` 就是「A 全部在前、B 全部在后」。归一化只让 B 层**跨 query** 可以设阈值、画直方图，并不把两层变成同一量纲。

**为什么归一化用理论上界，不用 min-max？**  
min-max 会让每个 query 的第一名都是 1.0，全局阈值没有意义。`s / Σ w_i/(k+1)` 在两路都第 1 时为 1.0，只在一路第 1 时为 0.5（等权），适合截断和观测。见 [tier-b.md](tier-b.md)。

**重排之后返回的 `score` 为什么还是 RRF 分？**  
协议规定给 Agent 的置信度必须是融合归一化结果，用于阈值和统计。重排只改顺序。要比对重排方案，看 `on_rerank` 事件，不要改 `ProseHit` 字段。

**`escalate_suggested = True` 时编排层该做什么？**  
本接口不规定。它只暴露「没有覆盖 / 最靠前规则要求转人工」。真转人工是 LangGraph 的事。

**`file_hint` 没用进 SQL，是漏了吗？**  
不是。字段已声明，实现可写日志。本协议改版前不要拼进 WHERE。

**C 层为什么不从这里查？**  
生命周期不同。C 层在 [`workspace_index/`](../../../workspace_index/README.md)。本 retriever 只读 `artifacts/rules.db` 和 `artifacts/corpora/`。

**能不能按报错类型换一套 WHERE？**  
不能。换 WHERE 骨架 = 换协议 = 和成品库不兼容。要加维度，先改 `RetrievalQuery` 和契约文档，再改 `query_rules`。

**`RetrievalMode.hybrid` 和 YAML `channels: hybrid` 是一回事吗？**  
不是。前者：开不开 A、开不开 B。后者：B 层内部 BM25 / 向量 / 两路。评测「纯关键词 vs 纯向量 vs 混合」扫的是 `channels`。见 [eval.md](eval.md)、[config.md](config.md)。

**生产可不可以传 `top_k: 8`？**  
不要。契约默认 8 是为了不删 Agent 字段。有 YAML 时传它会把「用 YAML 的 rerank_k=3」搞混。生产只填报错、符号、版本。评测覆盖条数用 `top_k_a` / `top_k_b` 或改 YAML。

**改 YAML 为什么必须进 cache_key？**  
同一句 `instance` + 同一份库，权重从 1:1 改成 1:2，答案集合会变。若不把 `config_hash` 编进 key，Redis 会返回旧权重的 hits。

**observer 默认 NoOp，是不是等于没留口子？**  
不是。router 每阶段仍调用方法。以后 `set_observer(PrometheusObserver())` 不必改 `tier_b.py`。见 [observability.md](observability.md)。
