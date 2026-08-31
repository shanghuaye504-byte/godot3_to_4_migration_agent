# Router 与运行时：融合、版本、校验、缓存、工具包装

对应脚本：[`router.py`](../router.py)、[`cache.py`](../cache.py)。版本函数在包根 `rag/version_codec.py`，不要复制进 retriever。

---

## 1. 默认不是「A 命中就短路」

已经改成：**默认一次调用同时查两层，两层都放进返回结果**。不要改回短路。

1. A 层命中一条改名，不代表 Agent 不需要 B 层上下文（例如 `change=default`）。
2. `agent_retrieval_or_escalate` 要求「A、B 都查过且都没有命中」才能作为 escalate 依据。
3. 评测要对比「只有 A / 只有 B / A+B」。生产若短路，线上和评测是两套东西。

`exact_only` / `semantic_only` 只留给评测，不是给 Agent 的日常参数。它们管的是开不开层，不是 B 内部 BM25 vs 向量（那是 YAML `channels`，见 [eval.md](eval.md)）。

---

## 2. `retrieve()` 控制流

实现时按这个写，不要发明第三层跨层排序。YAML、observer、A 层降级是相对旧伪代码的增量。

```text
t0 = now
observer = observer or get_observer()      # 默认 NoOp
config = config or load_config()           # 进程内已 load 的 YAML

symbols = query.symbols or extract_symbols(error_text)

# A 层。semantic_only 则跳过。
structured = []
if retrieval_mode != semantic_only:
    try:
        rows = query_rules(..., limit=effective_k_a, request_id=query.request_id)
        structured = [StructuredHit(rule, score_of, reason_of), ...]
    except Exception:
        error_log + observer.on_tier_a_error
        structured = []                    # 降级，继续 B

# B 层。exact_only 则跳过。
prose = []
if retrieval_mode != exact_only:
    prose = query_prose(..., config=config.tier_b, rerank_fn=..., observer=observer)

merged = 全部 A 的 UnifiedHit + 全部 B 的 UnifiedHit

coverage / recommended_action / escalate_suggested 按契约计算

observer.on_retrieve_end(...)
return RetrievalResult(..., cache_hit=False, took_ms=...)
```

`effective_k_a` / B 层最终条数的优先级见 [config.md](config.md)。`query_prose` 内部自己跑两路、RRF、阈值、重排；router **禁止**自己算 RRF。

`structured` 顺序来自 SQL `ORDER BY`；`prose` 顺序来自重排后的 B 层。`merged` 不做跨层插值：A 层是确定性事实，永远排在 B 层前面。

`extract_symbols()` 匹配：

- `Nonexistent function 'xxx'`
- `Invalid get index 'xxx'`
- `Identifier "xxx" not found`
- 反引号包裹的类型名

抠不出来时 `symbols` 允许为空：A 层 0 行，B 层仍用原文。

### A 层 score（与 B 层不同单位）

| 命中方式 | 建议分数 | 含义 |
| --- | --- | --- |
| `old_symbol` / `new_symbol` / `owner` 精确相等 | `1.0` | 字典对上了 |
| 只靠 `match_tokens` | 约 `0.7` | 挂钩词 |

B 层是归一化 RRF ∈ [0,1]。**两套不能比。**

---

## 3. 版本编解码：一份实现，写库和查库共用

```python
# rag/version_codec.py  — 包根，不要放进 build 或 retriever 的 schemas。

def version_to_code(v: str | None) -> int:
    if not v:
        return 0
    major, minor, *rest = (int(x) for x in v.split("."))
    patch = rest[0] if rest else 0
    return major * 10000 + minor * 100 + patch
```

三处必须调用这一份：

1. `build_tier_a.py` 写入 `since_version_code`
2. `RetrievalQuery.target_version_code`
3. `query_rules` / `query_prose` 的 `<=`

worker 镜像不带 `build/`，retriever **禁止** `import rag.build`。

---

## 4. 校验的三道防线

`schema_version`、`manifest.lock.json` 的文件哈希、`cache_key` 是三件不同的事。对照见 [docs/hash_and_manifest.md](../../../docs/hash_and_manifest.md)。

| 阶段 | 校验什么 | 失败怎么处理 |
| --- | --- | --- |
| adapter 写 JSONL | `MigrationRule.model_validate()` | build 失败 |
| `build_tier_a.py` 写库 | 再校验 + 写入 `meta.schema_version` | build 失败 |
| retriever 打开连接 | `meta.schema_version` == 代码期望 `"2"` | JSONL 后 `raise`，拒绝服务 |
| `query_rules` 逐行 | `model_validate` | skip + JSONL + 计数，见 [tier-a.md](tier-a.md) |
| `RetrievalQuery` 构造 | 版本格式、至少一个输入 | 抛给工具层，不吞 |
| `load_config()` | YAML 键合法 | 启动/评测加载失败，不默默夹紧 |

---

## 5. 缓存

`cache_key` 是门牌号，不是数据完整性校验。

```python
def cache_key(query, manifest_hash: str, config_hash: str) -> str:
    payload = query.model_dump_json(exclude={"request_id"})
    return sha256(f"{manifest_hash}:{config_hash}:{payload}")
```

- `manifest_hash`：已发布库的指纹（lock）。库 rebuild 后旧缓存打不中。
- `config_hash`：YAML 中影响召回的键。改权重必须换号。`log_dir` / `sample_rate` / `request_id` 不进指纹。见 [config.md](config.md)。
- 命中时只把 `cache_hit` 改成 `True`。
- worker 启动打开一次 `rules.db` 和 `corpus.lance`，不要每次检索重开。

---

## 6. 包成 Agent 工具

```text
LLM function-calling
    → RetrievalQuery
        → retrieve_cached()
            → router.retrieve()
                → extract_symbols()
                → tier_a.query_rules()     # 唯一 SQL
                → tier_b.query_prose()     # 唯一向量查询
                → observe.*
            → RetrievalResult
        → model_dump(JSON)
    → 回到 LLM
```

以后换成 MCP / REST，只改最外层外壳。
