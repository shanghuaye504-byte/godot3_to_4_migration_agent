# 在线观测：hook 使用手册

本轮**不实现**任何 sink（不写 JSONL 轨迹、不接 Prometheus、不接 OpenTelemetry）。但 router 的控制流必须在每一阶段调用 hook，默认是 `NoOpObserver`，这样后期加观测不必改检索路径。

签名与协议类写在 [`observe.py`](../observe.py) 的 docstring 里。A 层失败落盘是另一条、必须落地的日志通路，见 [tier-a.md](tier-a.md) 与 [`error_log.py`](../error_log.py)；它和「在线质量观测」互补：前者保证事故可查，后者给分数分布和召回质量留口。

---

## 1. 默认行为（实现时不要删掉）

- `router.retrieve()` **始终**持有一个 `RetrievalObserver`。调用方不传就是 `NoOpObserver`。
- YAML `observability.sample_rate` 默认 `0.0`：不把 `on_retrieve_end` 交给非 NoOp sink。
- `sample_rate=0` 时 **仍然调用** hook 方法。NoOp 的方法体是空的。这样「有没有人在听」和「检索走哪条路径」解耦。
- 禁止在 `tier_b.py` 里 `open("trace.jsonl")` 或 new 一个全局 logger 当观测。观测只从下面两个注册点进入。

---

## 2. 注册点（只有这两处）

### 单次调用

```python
# 示意：实现后的用法。本轮 retrieve() 会 raise NotImplementedError。
from rag.retriever.router import retrieve
from rag.retriever.observe import CompositeObserver

result = retrieve(query, observer=MyFileObserver(path), config=cfg)
```

`observer` 不是 `RetrievalQuery` 的字段。不要让 LLM 在工具 JSON 里填一个 observer 类名。

### 进程级默认

```python
from rag.retriever.observe import set_observer, get_observer, NoOpObserver

set_observer(MyPrometheusObserver())   # worker 启动时一次
# retrieve() 未传 observer 时用 get_observer()，默认 NoOpObserver()
```

`set_observer` / `get_observer` 的签名写在 `observe.py`。测试里要能换回 NoOp，避免泄漏到别的用例。

多个 sink 用 `CompositeObserver([a, b])`：按列表顺序转发同一事件。某个 sink 抛错不得打断检索——observer 内自己吞掉并记 error_log，或 Composite 捕获后继续。

---

## 3. 怎么写一个自定义 observer

实现 `RetrievalObserver` 协议上你关心的方法即可。不关心的方法保持空（NoOp 基类）。重排超参、Prom 的 bucket 边界、文件路径，全部放在 observer **自己的 `__init__`** 里，和 `RerankFn` 同一原则：对 retriever 透明。

下面三段都是**文档示例，不是本轮要提交的实现**。

### 示例 A：把分数落盘（以后做轨迹 JSONL 时照这个订 hook）

```python
class FileTraceObserver:
    def __init__(self, path: str) -> None:
        self.path = path  # 打开方式、轮转，都关在这里

    def on_retrieve_end(self, event: "RetrievalTraceEvent") -> None:
        # event.prose_hits 里已有归一化 score；raw RRF 在 event.fusion
        ...

    def on_fusion(self, event: "FusionEvent") -> None:
        ...
```

应订阅：`on_fusion`（原始 RRF + 归一化分）、`on_retrieve_end`（最终顺序）、可选 `on_rerank`。

### 示例 B：计数器 / 直方图（以后接 Prometheus）

```python
class CounterObserver:
    def on_retrieve_end(self, event: "RetrievalTraceEvent") -> None:
        # coverage、took_ms、score 直方图、no_hit、阈值丢掉条数
        ...

    def on_tier_a_error(self, event: "TierAErrorEvent") -> None:
        # rules_schema_drift_total += 1 这类
        ...
```

应订阅：`on_retrieve_end`、`on_tier_a_error`、`on_schema_skip`。

### 示例 C：以后接 OpenTelemetry

在 `on_retrieve_end` 里结束 span，属性带 `request_id`、`coverage`、`cache_hit`、`took_ms`。`on_channel_result` 可做 child span（bm25 / vector 各一次）。

---

## 4. 事件与检索阶段对应

```text
retrieve() 开始
  ├ on_retrieve_start          可选；有 request_id / config 快照即可
  ├ A 层
  │    ├ 成功 → 无强制 hook（命中写进 end 事件）
  │    ├ 整次失败 → on_tier_a_error + error_log JSONL
  │    └ 单行校验失败 → on_schema_skip + error_log JSONL
  ├ B 层
  │    ├ 每路原始结果 → on_channel_result（channel=bm25|vector）
  │    ├ 加权 RRF + 归一化 → on_fusion
  │    ├ 阈值丢掉之后、重排之后 → on_rerank
  └ 订好 RetrievalResult → on_retrieve_end
```

`sample_rate` **只**作用于「是否把 `on_retrieve_end`（以及你选择的高基数事件）交给非 NoOp sink」。`on_tier_a_error` / `on_schema_skip` 建议**永远转发**：事故日志不能被采样丢掉。A 层 JSONL（`error_log.py`）也不受 `sample_rate` 控制。

---

## 5. 事件字段（实现时按此建对象，本轮不写 Pydantic 类）

### `RetrievalTraceEvent`（`on_retrieve_end`）

| 字段 | 用途 |
| --- | --- |
| `request_id` | 与 Agent 步骤、verify 日志 join |
| `ts` | 墙钟 |
| `query_digest` | error_text / symbols / target_version / retrieval_mode；不要把整份报错无限加长 |
| `config_snapshot` | k、权重、channels、threshold、reranker 名 |
| `resolved_symbols` | 实际拿去查 A 的词 |
| `structured_hits` | `[{id, score, match_reason}, ...]` |
| `prose_hits` | `[{id, score, match_reason}, ...]`，`score` 为归一化 RRF |
| `coverage` / `recommended_action` / `escalate_suggested` | 与返回值一致 |
| `cache_hit` / `took_ms` | 成本 |
| `threshold_dropped` | 阈值丢掉多少条 |
| `channel_ranks` | 可选摘要；细节在 `on_channel_result` |
| `rerank_changed_top1` | 重排是否改了第一名 |

join key：`request_id` + `rule.id` / `chunk.id`。不要给 `RetrievalQuery` 加观测字段。

### `ChannelResultEvent`（`on_channel_result`）

`channel`（`bm25` 或 `vector`）、按该路顺序的 `chunk_id` 列表、该路原始分（若 Lance 提供；没有就只留名次）。

### `FusionEvent`（`on_fusion`）

每个候选：`chunk_id`、`rank_bm25`、`rank_vector`（缺席为 null）、`rrf_raw`、`score_normalized`。

### `RerankEvent`（`on_rerank`）

重排前 id 顺序、重排后 id 顺序、各 `rerank_score`。Agent 看到的 `ProseHit.score` **不是**这个数。

### `TierAErrorEvent` / `SchemaSkipEvent`

与 [tier-a.md](tier-a.md) JSONL 字段对齐：`event`、`error_type`、`error_message`、`rule_id`、`row_excerpt`、`symbols`、`target_version_code`、`request_id`。

---

## 6. 以后可接的 sink（现在不写代码）

| sink | 订阅哪些 hook | 回答什么 |
| --- | --- | --- |
| 采样轨迹 JSONL | `on_retrieve_end`（受 sample_rate）、`on_fusion` | 某次线上问句的分数长什么样 |
| Prometheus 直方图 | `on_retrieve_end`、`on_tier_a_error` | 归一化分数分布、p50/p95 延迟、`coverage=no_hit` 率、schema skip |
| OpenTelemetry span | start/end + channel child | 和 worker / LLM 调用串在一条 trace |
| 隐式反馈 join | `on_retrieve_end` 的 `request_id` | 这次检索之后 verify error 是否下降 |
| 金标影子评测 | 定时拿 eval 集走同一 `retrieve()` | 线上配置有没有漂 |
| LLM-as-judge 抽样 | 低 `sample_rate` 的 end 事件 | 高分段落是否真相关（贵，必须采样） |

没有这些 hook 时，上面每一项都得改 `tier_b.py`。所以空的 NoOp 调用是刚性的，不是装饰。

---

## 7. 和 A 层失败落盘的关系

| | `error_log.py` JSONL | `RetrievalObserver` |
| --- | --- | --- |
| 默认 | 写磁盘（事故） | NoOp |
| 受 sample_rate？ | 否 | 仅非事故的 end 事件 |
| 谁调用 | `tier_a` / router 在 catch 里 | router 各阶段 |
| 内容 | 异常、脏行 | 分数、名次、覆盖率 |

两者都要留。observer 的 `on_tier_a_error` 可以以后再抄一份到 Prom；磁盘 JSONL 是人排查的底线，实现 `query_rules` 时就必须写。
