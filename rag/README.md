# rag：A/B 层（官方知识检索）

RAG 组件做成一个可以被本地直接 `import` 的 Python 包（library），再在 Agent 层用一个很薄的「工具函数」包一层，而不是做成一个独立跑起来的网络服务。

两份细化协议文档：数据库一行长什么样、四类源怎么编译成这一行，看 [rag/build/README.md](build/README.md)；一次检索怎么同时召回结构化规则和语义段落、Agent 怎么调用、YAML 怎么配，看 [rag/retriever/README.md](retriever/README.md)。架构与脚本边界看 [retriever/ARCHITECTURE.md](retriever/ARCHITECTURE.md)，字段级协议在 [retriever/docs/](retriever/docs/README.md)。本文件只讲目录职责和总体工作流，不重复那些文档的细节。

一句话记忆：`vault` 是原材料仓库，`build` 是工厂产线，`artifacts` 是出厂成品，`retriever` 是成品的说明书 + 使用接口。Agent 和 worker 永远只碰 `retriever` 和 `artifacts`，不需要知道 `vault` 和 `build` 的存在。

## 设计结论

先分清「建库」和「用库」是两件事，别混在一个目录里跑。原始数据、解析代码、检索代码全堆在一起时，Day 5 把 worker 打进 Docker 镜像分布式跑，镜像里会被迫带上一堆运行时根本用不到的东西（例如 clone Godot 源码用的 git 逻辑、解析 rst 文档用的库）。

所以把 `rag/` 拆成四个生命周期完全不同的部分：

| 目录 | 生命周期 | 谁用 |
|------|----------|------|
| `vault/` | 原始数据，只读；人工维护 + 定期从官方仓库拉取 | 只在本机 build 时读 |
| `build/` | 「编译」脚本：读 vault，产出 artifacts | 只在本机跑，不进生产镜像 |
| `artifacts/` | build 的产出物：SQLite + LanceDB，不可变 | 整份打进镜像 |
| `retriever/` | Agent 运行时被调用的库：只读 artifacts，依赖很轻 | 每个 worker 进程 |

`build/` 依赖 `requests`、GitPython、rst 解析器这些「重」依赖，而且只用一次（或者每次升级 Godot 版本目标时才重跑一次）。`retriever/` 运行时依赖：lancedb + sqlite3 + pydantic + pyyaml（读 YAML）+ fastembed（`query_embed`，与建库同一 BGE 模型）。build 专用的 docutils / requests / GitPython 仍只在 `build` 依赖组。

## 目录职责

```
rag/
├── vault/
│   ├── manifest.json                    # 记录三个版本 tag：godot 二进制版本、godot-docs checkout 版本、
│   │                                     #   extension_api.json 对应版本，build 时校验三者是否对齐
│   ├── tier_a_official/                 # 官方可机读的源文件，原样存一份快照（不是每次现拉）
│   │   ├── renames_map_3_to_4.cpp
│   │   ├── extension_api_4.0.json
│   │   ├── extension_api_target.json
│   │   └── upgrading_to_godot_4.x.rst   # 各小版本升级指南
│   ├── tier_a_manual/                   # 人工补充，YAML/JSON 维护，「陷阱规则」
│   │   ├── semantic_rewrites.yaml       # yield→await、move_and_slide 等语义重构
│   │   └── known_traps.yaml             # extents→size 数值陷阱、假阳性名单等，带 source_url 字段
│   └── tier_b_prose/                    # 散文原材料，两类来源都在这：人工维护的原文（docs 全文、
│                                         #   精选 issue、社区笔记）+ build 解析 4.x rst 时顺手抽出的
│                                         #   非结构化段落（*.prose.jsonl，按标题预分段，见 build/README.md 6.3/6.4）
│
├── build/
│   ├── parse_renames_cpp.py             # 解析 renames_map_3_to_4.cpp → 规则行
│   ├── diff_extension_api.py            # 两份 api json 做 diff → 版本差异规则
│   ├── parse_upgrading_docs.py          # rst 表格拆分：结构化行进 intermediate/，散文写入 vault/tier_b_prose/
│   ├── build_tier_a.py                  # 读 intermediate/ + YAML → 写 SQLite（本阶段唯一写库的程序）
│   ├── intermediate/                    # 编译中间行（jsonl），不进生产镜像，只服务 rules.db 这一步
│   ├── chunk_prose.py                   # B 层：IR + 类型 A jsonl → artifacts/chunks/<id>/
│   ├── embed_prose.py                   # B 层：jsonl → artifacts/corpora/<id>/corpus.lance
│   ├── chunk_and_embed.py               # 薄封装：默认策略先 chunk 再 embed
│   ├── build_tier_b.py                  # 下一阶段：写 LanceDB，建索引
│   └── build_all.sh                     # 一键跑完，最后校验 manifest 三版本号一致
│
├── artifacts/                           # 不手写，只能由 build/ 生成；整份可以当不可变文件打进镜像
│   ├── rules.db                         # SQLite，Tier A
│   ├── agent_context/                   # 不入库的整篇文档，Agent 常驻上下文
│   │   └── upgrading_to_godot_4.rst     # 3→4 总指南，除 Updating shaders 小节外整篇存这里
│   ├── chunks/<strategy_id>/            # 切块落盘（chunks.jsonl + manifest.json）
│   ├── corpora/<strategy_id>/           # 各策略独立 LanceDB（corpus.lance）
│   ├── corpus.lance/                    # 仅 default 策略的兼容镜像
│   └── manifest.lock.json               # 存 vault 各文件的 hash + 构建时间；和 vault/manifest.json、
│                                        #   cache_key、schema_version 不是同一件事，对照见 docs/hash_and_manifest.md
│
├── retriever/                           # 可调用组件本体，做成一个能被 import 的包
│   ├── README.md                        # 使用者入口：调用、YAML、hook
│   ├── ARCHITECTURE.md                  # 架构与模块地图
│   ├── retriever.yaml                   # 运行时唯一调参（k / 权重 / 通道 / 阈值）
│   ├── docs/                            # 字段级协议（tutorial / contracts / tier-a / tier-b / …）
│   ├── __init__.py
│   ├── schemas.py                       # 枚举 + MigrationRule + ProseChunk + RetrievalQuery/Result
│   ├── config.py                        # 读 retriever.yaml，config_hash
│   ├── tier_a.py                        # 唯一 SQL
│   ├── tier_b.py                        # 两路召回 + 加权 RRF
│   ├── rerank.py                        # RerankFn（identity / minilm_l6）
│   ├── router.py                        # retrieve() / load()：两层同时查、订结果
│   ├── cache.py                         # key = hash(库指纹 + 配置指纹 + query)
│   ├── observe.py                       # RetrievalObserver，默认 NoOp
│   └── error_log.py                     # A 层失败 JSONL
│
├── test/                                # pytest 单元/不变量测试（默认 ``pytest`` 只扫这里）
│   ├── conftest.py                      # 把 rag/build 放进 sys.path
│   ├── test_build_artifacts.py          # A 层 rules.db 不变量（缺库则 skip）
│   ├── test_prose_preprocessing_util.py
│   ├── test_tier_b_processors.py
│   └── test_chunk_and_embed.py
│
├── eval/                                # 离线召回评测，不是 pytest 套件
│   ├── gen_eval_set.py                  # 机械生成 E1/E2/E3（直接读 artifacts/rules.db 反推）
│   ├── hard_cases.yaml                  # 人工标的 E4
│   └── run_ablation.py                  # 跑消融实验，输出 markdown 报告表
│
└── pyproject.toml                       # 把 retriever/ 声明成可 `pip install -e .` 的本地包
```

## 运行时形态：工具，不是独立服务

做成一个 Agent 工具（function calling 里的一个 tool）。工具内部直接 `import` `retriever` 包，不需要包成一个独立运行的网络服务。理由分三层：

### 1. 技术上没必要起服务

LanceDB 和 SQLite 都是嵌入式、文件形态的存储，不是「要连一个数据库地址」的那种服务。Day 5 起多个 worker 进程时，每个 worker 自己在本地 `import rag.retriever` 就能直接读同一份 `artifacts/`（多进程并发只读完全没问题，因为运行时不写）。

如果专门为它包一层 FastAPI 服务，反而是多加了一个网络依赖：多一次 HTTP 往返的延迟，多一个要写熔断和超时处理的失败点，而且这个服务本身还要考虑要不要也做成多副本、要不要放到 Day 5 那套 Redis 熔断体系里管理。收益是零。

### 2. 集成到 Agent 的样子

在 Day 3 的 LangGraph 里，Agent 直接看到的工具非常薄。真正的检索逻辑（A、B 两层怎么同时查、怎么融合排序）完全封装在 `retriever/router.py` 里，Agent 不需要也不应该知道内部分了 A/B 两层。

```python
# rag_tool.py，是 Agent 直接看到的「工具」，非常薄
from rag.retriever import retrieve_cached, RetrievalQuery

@tool(args_schema=RetrievalQuery)
def retrieve_migration_rule(**kwargs) -> dict:
    """输入一条 verify 阶段的报错信息或已知符号，返回相关的迁移规则"""
    return retrieve_cached(RetrievalQuery(**kwargs)).model_dump(mode="json")
```

Agent 眼里，这就是一个普通的工具调用，跟它去读文件、跑 verify 没有本质区别。字段、融合、`escalate_suggested` 见 [retriever/docs/](retriever/docs/README.md) 与 [ARCHITECTURE.md](retriever/ARCHITECTURE.md)，这里不重复。

### 3. 接口协议要设计得「服务无关」

这样以后要升级成服务也不用大改。具体做法：`retriever/schemas.py` 里定义好的 `RetrievalQuery`（输入）和 `RetrievalHit`（输出）这两个 Pydantic 模型，就是系统里唯一的「契约」。

今天它们是被 Python 函数直接调用的参数/返回值；如果哪天真的需要把它包成 MCP server 或者一个 REST 接口（例如以后 judge 模块想用别的语言写、需要跨进程访问），只需要在外面加一层薄薄的适配器（FastAPI 路由或 MCP tool handler），把 HTTP body / MCP 参数转换成同一个 `RetrievalQuery`，内部逻辑一行都不用改。

协议指的是这两个 Pydantic schema，不是现在就要起个 HTTP server。

## Worker 启动时加载一次、复用多次

在 Day 5 分布式场景下，每个 fix-worker 进程启动时应该只连接一次 `artifacts/rules.db` 和 `artifacts/corpus.lance/`（建议在 `retriever/__init__.py` 里做一个进程级别的单例，或者显式的 `load()` 函数），然后处理这个 worker 分到的所有任务时反复复用同一个连接/索引句柄。

不要每次调用工具都重新打开一次文件——重新打开 LanceDB 索引这个动作本身有一定开销，在高并发下会成为不必要的瓶颈。这是「库」和「服务」在使用方式上唯一需要手动注意的地方：服务天然是常驻的，库需要自己保证它在进程生命周期内只初始化一次。

## 和 C 层的边界

C 层（符号表、场景树、依赖图）不放进 `rag/` 目录，因为它的生命周期和 A/B 两层完全不同：

- A/B 层是「建一次、所有仓库共用」
- C 层是「每个仓库现建、用完就扔」

C 层在平级目录 [`workspace_index/`](../workspace_index/README.md)，同样暴露成几个 Agent 工具，但底层实现和 `rag/retriever` 完全独立，不共享存储。两者只在「都是 Agent 工具」这一点上是同类，内部实现没有必要耦合在一起。

## A 层编译工作流

`tier_a_official/` 和 `tier_a_manual/` 都是 vault 原材料，**一起编译**进 `artifacts/rules.db`。manual 里的 YAML 不是编译完再往成品里手抄的备忘：「人工」只发生在写 YAML，不发生在改 SQLite。改陷阱或语义重构 → 改 YAML → 重新跑 `build_tier_a.py`。

陷阱怎么分流（进 Agent 检索、进 L0 后静态扫描器、进 verify 出口过滤器，还是干脆不入库只留 vault 当档案）由 `detection_method` 这一列决定，不是靠某个布尔标记列。完整列设计、DDL、每种官方源怎么填表，权威版本是 [build/README.md](build/README.md)，本文件不重复。

### 多个前端，一种中间行，一个后端

cpp / rst / json / yaml 形状不同，**不是同一个解析器**。各写一个 adapter，产出中间 JSONL（`build/intermediate/*.jsonl`），由 `build_tier_a.py` 合并写入 `rules.db`。

```text
renames_map_3_to_4.cpp          → parse_renames_cpp.py     ─┐
upgrading_to_godot_4.{1-7}.rst  → parse_upgrading_docs.py   ├─► intermediate/*.jsonl ─► build_tier_a.py ─► rules.db
extension_api_*.json            → diff_extension_api.py    │
tier_a_manual/*.yaml            → yaml.safe_load           ─┘
```

`parse_upgrading_docs.py` 多一个出口：rst 里抽不出符号对、只是散文说明的段落不进 `intermediate/`，写进 `vault/tier_b_prose/`——那是**下一阶段** B 层编译要读的原材料，不是这一步的产物（这一步只编译 A 层）。

### YAML：每条都是新插入一行，不做 overlay

不再用 `op: overlay` 去改已有行（例如在 extents→size 那条改名上打个语义风险标记）。每一条 YAML 都是独立 `insert` 一行，靠 `detection_method` 告诉系统这一行该由谁读；理由和完整示例见 [build/README.md 第 3、8 节](build/README.md)。当前的 [`semantic_rewrites.yaml`](vault/tier_a_manual/semantic_rewrites.yaml) 已经是这个格式，不含 `op` 字段。

### 和官方源怎么对齐

| 来源 | adapter 主要填什么 | `source` |
|------|-------------------|----------|
| `renames_map_3_to_4.cpp` | `owner/old_symbol/new_symbol/symbol_kind`，`since_version=4.0` | `official_renames`（注释掉的条目 `official_renames_skipped`） |
| `upgrading_to_godot_4.{1-7}.rst` | 变更描述、`since_version`（按文件名）、兼容性、GH 编号；7 份拍平进同一张表，不让 Agent 连跳 7 次 | `official_prose` |
| `upgrading_to_godot_4.rst` 的 `Updating shaders` 例外 | 唯一从这篇 3→4 总指南里抽出来占行的部分，见 [build/README.md 6.4](build/README.md) | `official_prose_3to4_shader` |
| `extension_api_4.0.json` vs `extension_api_target.json` | 删类/改签名/新增 | `api_diff` |
| YAML `insert` | 整行：假阳性、converter 缺口、语义重构骨架 | `manual_trap` / `manual_rewrite` |

查表：`old_symbol` / `new_symbol` / `owner` / `match_tokens` 命中，且 `since_version_code <= target_version_code`（版本比较一律走编码后的整数，禁止直接比字符串——`"4.10" < "4.9"` 会错）。同一符号多条规则按 `since_version_code` 降序。rst 与 API diff 允许重叠，靠 `source` 区分，不必强行去重。

## 开发环境：用 uv 管理这个包

`rag/` 是一个独立的 uv 项目（`rag/pyproject.toml` + `rag/uv.lock`），和仓库根目录、`workspace_index/` 各自管自己的依赖，不共享一个虚拟环境——原因见上面「设计结论」那一节:`build/` 和 `retriever/` 的依赖轻重差太多，不能装在一起。

### 包名和目录的对应关系

`rag/pyproject.toml` 和 `rag/retriever/`、`rag/build/` 平级，同在 `rag/` 这一层，**没有**再套一层 `rag/rag/`。但 `import` 出来的顶层包名仍然是 `rag`（`from rag.retriever import ...`、`from rag.version_codec import ...`）——这靠 `pyproject.toml` 里 `[tool.setuptools] package-dir = {"rag" = "."}` 做到:告诉 setuptools「`rag` 这个包名，映射到当前目录本身」，`packages` 显式只列 `["rag", "rag.retriever"]`,所以 `build/`、`vault/`、`artifacts/`、`eval/`、`test/` 不会被打进 wheel。具体原理和实测记录写在 `pyproject.toml` 文件里的注释里,改这块配置之前先看那段注释。

### 三条常用命令

```bash
cd rag

# 本机开发：运行时依赖 + build 脚本依赖（docutils/pyyaml/requests/gitpython）+ 测试工具（pytest/ruff），可编辑安装
uv sync --group build --group dev

# 只装运行时依赖，模拟 worker 镜像会装的那一份（不带任何 build-only 的重依赖）
uv sync --no-default-groups

# 出生产用的 wheel：Docker 镜像装这个，不要 -e，不会带 vault/build/artifacts 源码
uv build --wheel -o dist/
```

`uv sync`（不加任何 `--group`/`--no-*` 参数）会隐式装上 `dev` 组——这是 uv 的历史默认行为（`dev` 是特殊组名），自定义组名（这里的 `build`）不会被隐式装上，必须显式 `--group build`。想验证"只装运行时依赖"时不要漏了 `--no-default-groups` 这个参数,否则会把 `pytest`/`ruff` 也算进去。

### 依赖分组对应关系

| 依赖组 | 内容 | 谁用 | 是否进 worker 镜像 |
|---|---|---|---|
| `[project.dependencies]`（无组名，基础依赖） | `pydantic`、`lancedb` | `retriever/` 运行时 | ✅ 必须带 |
| `[dependency-groups] build` | `docutils`、`pyyaml`、`requests`、`gitpython` | `build/` 里的 adapter 脚本 | ❌ 不带 |
| `[dependency-groups] dev` | `pytest`、`ruff` | 本机测试/lint | ❌ 不带 |

具体每个 adapter 用哪个库解析哪种源文件、为什么这么选，见 [build/PARSING.md](build/PARSING.md)。

### `uv.lock` 要提交，`.venv/`、`dist/` 不要

`rag/uv.lock` 锁的是三个依赖组解析出来的精确版本，跟着代码一起提交，保证任何人 `uv sync` 出来的环境一致。`.venv/`、`dist/`、`*.egg-info/`、`__pycache__/` 都是本机产物，已经写进根目录 `.gitignore`，不需要手动排除。
