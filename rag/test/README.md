# test：rag 的 pytest 套件

工程正确性测试（parser / filter / chunker / A 层 `rules.db` 不变量），**不是**检索召回评测。召回率、消融、评测集在 [`../eval/`](../eval/README.md)。

`rag/pyproject.toml` 的 `testpaths = ["test"]`：在 `rag/` 下直接 `pytest` 只扫本目录。

## 怎么跑

```bash
cd rag
uv sync --group build --group dev
.venv/bin/pytest -v --tb=short
```

必须用 `rag/.venv`，不要在仓库根目录 `uv run pytest`。

| 文件 | 覆盖 |
| --- | --- |
| `conftest.py` | 把 `rag/build` 放进 `sys.path`；每个用例重置 retriever 进程态 |
| `test_chunk_and_embed.py` | 装箱、code 绑定、`ProseChunk`、jsonl roundtrip |
| `test_retriever_config.py` | YAML 校验、`config_hash` |
| `test_retriever_tier_a.py` | SQL 死门、版本过滤、脏行 skip |
| `test_retriever_tier_b.py` | RRF 归一化、临时 Lance 混合检索 |
| `test_retriever_router.py` | 抠符号、覆盖率、A 降级、缓存、observer |
| `test_retriever_smoke.py` | 对真实 `artifacts/rules.db` 做 exact_only 冒烟 |

本目录不打进 wheel。教学笔记见 [`docs/pytest_tier_b_walkthrough.md`](../../docs/pytest_tier_b_walkthrough.md)。
