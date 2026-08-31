# Agent 契约：枚举、`RetrievalQuery`、`RetrievalResult`

这些形状是冻结的 Agent / 工具边界。实现 `retrieve()`、工具函数、以后的 HTTP 适配器，都只收 `RetrievalQuery`、只交 `RetrievalResult`。

**本轮不把 `RetrievalQuery` / `RetrievalResult` / `ProseHit` 写成 Pydantic 类。** 权威就是本文。`schemas.py` 里已经落地的是枚举 + `MigrationRule` + `ProseChunk`，与 [build/README.md](../../build/README.md) DDL 和 [CHUNKING.md](../../vault/tier_b_prose/CHUNKING.md) 对齐。不要在本轮给那些已有类加字段。

权重、`recall_k`、`rerank_k`、通道、阈值、observer **不出现在这张表里**。见 [config.md](config.md)。

---

## 1. 运行时会出现的几张「只准勾选的名单」

写在 `rag/retriever/schemas.py`。实现检索时不要新增枚举成员——那等于改 schema，会和已经生成的 `rules.db` 对不上。

```python
class SymbolKind(str, Enum):
    """这条规则描述的是「哪一类符号」。和 change（发生了什么）必须拆开。"""
    class_ = "class"
    method = "method"
    property = "property"
    signal = "signal"
    enum = "enum"
    constant = "constant"
    builtin = "builtin"
    shader = "shader"
    theme = "theme"
    color = "color"
    project_setting = "project_setting"
    singleton = "singleton"
    utility = "utility"
    rewrite = "rewrite"
    trap = "trap"


class ChangeKind(str, Enum):
    rename = "rename"
    remove = "remove"
    add = "add"
    signature = "signature"
    type = "type"
    move = "move"
    split = "split"
    replace = "replace"
    default = "default"
    behavior = "behavior"
    rewrite = "rewrite"
    trap = "trap"
    false_positive = "false_positive"


class DetectionMethod(str, Enum):
    """「谁有权看见这一行」。Agent 的 retrieve_migration_rule 只能看见前两种。"""
    agent_retrieval = "agent_retrieval"
    agent_retrieval_or_escalate = "agent_retrieval_or_escalate"
    static_scan_post_l0 = "static_scan_post_l0"
    verify_error_filter = "verify_error_filter"
    not_actively_handled = "not_actively_handled"
    preflight_probe_recommended = "preflight_probe_recommended"


class AgentAction(str, Enum):
    apply_rename = "apply_rename"
    apply_and_warn = "apply_and_warn"
    do_not_fix = "do_not_fix"
    escalate_human = "escalate_human"
    note_only = "note_only"


AGENT_VISIBLE_DETECTION_METHODS = (
    DetectionMethod.agent_retrieval,
    DetectionMethod.agent_retrieval_or_escalate,
)
```

为什么「陷阱不能让 Agent 检索到」要做成「类型上就不存在」：ReAct 循环的燃料是报错信号。`RectangleShape2D.extents → size` 改完名字之后编译器不再报错，但碰撞盒已经错了一半。这类检查必须离开循环，交给 L0 之后的确定性扫描器。扫描器另写 `WHERE detection_method = 'static_scan_post_l0'`，**不经过** `RetrievalQuery`。细节见 [build/README.md 第 1 节](../../build/README.md)。

---

## 2. `RetrievalQuery`：Agent 唯一能填的那张表

```python
class RetrievalMode(str, Enum):
    hybrid = "hybrid"                # 默认。A、B 两层都查，两层都返回。生产路径只用这个。
    exact_only = "exact_only"        # 只查 A 层。给「只有字典」消融用，不是给 Agent 用的。
    semantic_only = "semantic_only"  # 只查 B 层。同样只给消融用。


class RetrievalQuery(BaseModel):
    error_text: str | None = None
    # verify / import 抛出的原始报错全文。
    # 若 symbols 为空，extract_symbols() 从这段文字里抠符号；
    # 查 B 层时优先用这段文字做 query_embed / BM25。

    symbols: list[str] = Field(default_factory=list)
    # 已认得的旧符号名。原样交给 A 层 IN (...) 。
    # 允许为空：抠不出来 A 层就 0 行。

    query_text: str | None = None
    # 自由文本，不是针对某一条报错。主要喂给 B 层。

    target_version: str
    # 形如 "4.7.1" 或 "4.7"。真正比较的是 target_version_code。

    file_hint: str | None = None
    # 触发报错的路径提示。当前协议没有为它加 WHERE；不要擅自 LIKE。

    kinds: list[SymbolKind] | None = None
    # 非空时 tier_a 才追加 AND symbol_kind IN (...)。

    retrieval_mode: RetrievalMode = RetrievalMode.hybrid
    # 默认两层都查。不是「先查 A，命中了就不查 B」。
    # 这不是 YAML 的 tier_b.channels。见 config.md。

    top_k: int = 8
    # 契约里保留，默认 8。生产路径有 YAML 时不要传这个字段。
    # 仅当 YAML 缺失时，作为两层最终条数的兜底。见 config.md 优先级。

    top_k_a: int | None = None
    # 非空则覆盖 YAML 的 tier_a.top_k。

    top_k_b: int | None = None
    # 非空则覆盖 YAML 的 tier_b.rerank_k（B 层最终条数）。
    # 不覆盖 recall_k、不覆盖 BM25/向量各路的 k。

    request_id: str | None = None
    # 追踪号。不算进缓存 key。观测 join 靠它。
```

校验（实现 Pydantic 时照此）：

- `target_version` 只接受 `\d+\.\d+(\.\d+)?`，拒绝 `4.7-rc1`、`latest`。
- `top_k` / `top_k_a` / `top_k_b`：非空则 1～50。
- `error_text` / `symbols` / `query_text` 至少一个非空。
- `target_version_code` 为计算字段：`version_to_code(target_version)`。

### 这张表刻意没有的东西

- 没有 `sql` / `where` / `filters: dict`。
- 没有 `detection_method`。调用方无法要 `static_scan_post_l0`。
- 没有 `bm25_weight` / `recall_k` / `score_threshold` / `reranker` / `observer`。
- `retrieval_mode` 默认不是短路。原因见 [router-runtime.md](router-runtime.md)。

---

## 3. `RetrievalResult`：还给 Agent 的唯一出参

```python
class StructuredHit(BaseModel):
    rule: MigrationRule
    score: float                 # A 层命中方式置信度：精确列 1.0，仅 match_tokens 约 0.7
    match_reason: str            # "old_symbol" / "new_symbol" / "owner" / "match_tokens"


class ProseHit(BaseModel):
    chunk: ProseChunk
    score: float
    # RRF 上界归一化后的 [0, 1]。只能在 B 层内部比，不能和 A 层 1.0 比。
    # 重排只改顺序，不改这个字段。
    match_reason: Literal["bm25", "vector", "hybrid"]


class UnifiedHit(BaseModel):
    layer: Literal["A", "B"]
    score: float
    structured: MigrationRule | None = None
    prose: ProseChunk | None = None


class RetrievalResult(BaseModel):
    resolved_symbols: list[str]
    target_version_code: int
    structured_hits: list[StructuredHit]
    prose_hits: list[ProseHit]
    merged: list[UnifiedHit]
    # 先全部 A，再全部 B。长度上限 = A 最终条数 + B 最终条数。
    coverage: Literal["rule_hit", "prose_only", "no_hit"]
    recommended_action: AgentAction | None
    escalate_suggested: bool
    cache_hit: bool
    took_ms: float
```

`coverage`：

- `rule_hit` → 有 A 层命中
- `prose_only` → 只有 B
- `no_hit` → 都没有

`escalate_suggested`：`coverage == "no_hit"` 或 `recommended_action == escalate_human`。工具本身不据此决策。

> 检索服务只负责把事实报告清楚，不擅自替 Agent 做决定。

### Agent 读 A 层时最有用的 `MigrationRule` 字段

完整列定义以 [build/README.md 第 4～5 节](../../build/README.md) 为准。

| 字段 | Agent 拿它干什么 |
| --- | --- |
| `id` | 引用；judge 核对 |
| `old_symbol` / `new_symbol` / `owner` | 改哪个词 |
| `symbol_kind` / `change` | 改名还是重写 |
| `warning` / `snippet` | 一并给模型看 |
| `agent_action` | 抄到 `recommended_action`（仅第一条） |
| `semantic_risk` / `converter_gap` / `verifier_blind` | 风险标记 |
| `source` / `source_url` / `confidence` | 溯源 |
| `payload` | 源特定细节。**不参与 WHERE** |
| `trigger` / `system_action` | 给扫描器的；Agent 不必用 |
