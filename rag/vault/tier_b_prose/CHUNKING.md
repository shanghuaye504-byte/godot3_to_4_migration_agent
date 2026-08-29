# B 层 Prose 预处理工作手册

> 本手册是 `rag/vault/tier_b_prose/` 的**唯一本地协议**。它指导维护者如何把 `_raw/` 下 21 个异构源文件预处理成统一的 Document IR，再交给 `chunk_and_embed.py` 装箱。
>
> 设计目标：小规模（≈21 文件）下极度简化，不引入工作流引擎、LLM 层或统一编排器；同时保留 IR 统一出口和 chunker 统一性，未来扩展到 200 文件时只需逐个桶加规则，不需要重写架构。
>
> 参考文档：
>
> - 语料清单与来源说明：[README.md](README.md)
> - HTML/RST/Markdown 提取示例：[docs/prose_preprocessing_guide.md](../../../docs/prose_preprocessing_guide.md)
> - 检索侧契约：[rag/retriever/README.md](../../retriever/README.md)
> - A 层规则库契约：[rag/build/README.md](../../build/README.md)

---

## 1. 总体设计

### 1.1 一句话总结

**文件夹即分类**：`_raw/` 下 7 个来源文件夹天然对应 7 个处理桶；每个桶由一个独立的 `process_*.py` 脚本处理；公共能力下沉到 `rag/build/prose_preprocessing_util/`；所有桶最终产出同一种 `ir/*.ir.json`。

### 1.2 三阶段流水线

```mermaid
flowchart LR
    raw["_raw/ 7 个来源文件夹"] --> scanner["scan_tier_b_raw.py<br/>格式归一化"]
    scanner --> ap["after_preprocess/<bucket>/<file>.blocks.jsonl"]
    ap --> proc["process_<bucket>.py<br/>filter / select / HITL"]
    proc --> ir["ir/<bucket>/<file>.ir.json"]
    ir --> chunker["chunk_and_embed.py<br/>单一 chunker"]
    chunker --> lance["artifacts/corpus.lance"]

    proc -.->|F/G only| queue["review_queue.jsonl"]
    queue -.->|human| curation["curation/<stem>.yaml"]
    curation -.->|compile_curation.py| ir
```




| 阶段             | 做什么                                              | 入口脚本                  | 产物                                              |
| -------------- | ------------------------------------------------ | --------------------- | ----------------------------------------------- |
| 1. 格式归一化       | 按扩展名把 rst/html/md 解析成带 `heading_path` 的 block 草稿 | `scan_tier_b_raw.py`  | `after_preprocess/<bucket>/<file>.blocks.jsonl` |
| 2. 桶级处理        | 每个桶独立 filter/select；官方源直接写 IR；社区源生成 review queue | `process_<bucket>.py` | `ir/*.ir.json` 或 `review_queue.jsonl`           |
| 3. 编译 Curation | 把人工确认后的 curation YAML 编译成 IR                     | `compile_curation.py` | `ir/community_*/*.ir.json`                      |
| 4. 切块 + Embedding | 读全部 IR + lift 类型 A，统一 chunk，生成向量，写入 LanceDB   | `chunk_and_embed.py`  | `artifacts/corpus.lance`                        |




### 1.3 为什么这样设计

- **不建统一编排器**：21 个文件不需要 DAG。7 个桶脚本可以逐个实现、逐个调试。
- **不建来源清单文件**：`_raw/` 下 7 个文件夹名就是清单，新增来源时新建文件夹即可。
- **不引入 LLM**：当前规模规则 + 人工即可；review_queue 就是人工入口，未来如需 LLM 只需在 `process_community.py` 里加一个候选生成函数。
- **逻辑与产物分离**：所有 `process_*.py` 放在 `rag/build/`，所有中间产物放在 `rag/vault/tier_b_prose/` 下，便于审计和重跑。

---



## 2. 目录结构



### 2.1 `rag/vault/tier_b_prose/`

```text
rag/vault/tier_b_prose/
├── _raw/                              # 原始快照，只读
│   ├── official_upgrading_guide/      # 8 篇 rst + 8 个 *.prose.jsonl（类型 A）
│   ├── official_gdscript_doc/         # 3 篇 rst（类型 B）
│   ├── official_html_doc/             # 3 个 html（类型 C）
│   ├── official_blog/                 # 2 个 html（类型 D）
│   ├── github_pr/                     # 2 个 API Markdown（类型 E）
│   ├── github_issue/                  # 2 个 API Markdown（类型 E）
│   ├── github_discussion/             # 1 个 API Markdown（类型 E）
│   ├── community_blog/                # 7 个 html（类型 F）
│   └── community_gist/                # 1 个 html（类型 G）
│
├── after_preprocess/                  # scanner 输出，结构化 block 草稿
│   ├── official_gdscript_doc/
│   ├── official_html_doc/
│   ├── official_blog/
│   ├── github_pr/
│   ├── github_issue/
│   ├── github_discussion/
│   ├── community_blog/
│   └── community_gist/
│
├── policy/                            # 可选规则文件
│   ├── heading_allowlist.yaml
│   ├── heading_denylist.yaml
│   ├── keyword_allowlist.yaml
│   ├── boilerplate_patterns.txt
│   ├── maintainer_logins.yaml
│   └── topic_map.yaml
│
├── curation/                          # F/G 人工确认后的真相源
│   └── (人工维护，初始为空)
│
├── ir/                                # 最终 Document IR
│   ├── official_gdscript_doc/
│   ├── official_html_doc/
│   ├── official_blog/
│   ├── github_pr/
│   ├── github_issue/
│   ├── github_discussion/
│   ├── community_blog/
│   └── community_gist/
│
├── CHUNKING.md                        # 本手册
└── README.md
```



### 2.2 `rag/build/` 新增文件

```text
rag/build/
├── prose_preprocessing_util/          # 公共组件
│   ├── __init__.py
│   ├── ir.py                          # Document IR schema 与读写
│   ├── filters.py                     # 公共 filter
│   ├── selectors.py                   # 公共 select
│   ├── parsers.py                     # rst/html/md 统一解析入口
│   ├── heading_path.py                # heading_path 栈
│   └── review_queue.py                # review_queue.jsonl 读写
│
├── scan_tier_b_raw.py                 # 阶段 1：扫描 + 格式归一化
├── download_github_api.py             # 类型 E：API → _raw/*.md
├── process_official_gdscript_doc.py   # 类型 B
├── process_official_html_doc.py       # 类型 C
├── process_official_blog.py           # 类型 D
├── process_github.py                  # 类型 E（只滤 jsonl）
├── process_community.py               # 类型 F/G
├── compile_curation.py                # 阶段 3：YAML → IR
└── chunk_and_embed.py                 # 阶段 4：读 IR + lift A → chunk
```

---



## 3. Document IR 设计

IR 是预处理的唯一出口。每个源文件对应一份 `ir/<bucket>/<source_file>.ir.json`（类型 A 除外，用 `.prose.jsonl` 退化 IR 直接 lift）。

### 3.1 设计原则

1. **按块建模，不按 token**：chunker 才负责 token 长度，IR 只保留语义块。
2. **保留 heading_path**：块必须带完整标题路径，chunker 按路径装箱。
3. **code 原子**：代码块作为独立 block，不提前与 prose 合并。
4. **来源可追溯**：IR 中保留 `source`、`source_type`、`source_file`、`source_url`。



### 3.2 文档级字段


| 字段               | 类型             | 必填    | 说明                                      |
| ---------------- | -------------- | ----- | --------------------------------------- |
| `schema_version` | `int`          | 是     | 当前为 `1`。                                |
| `doc_id`         | `string`       | 是     | 稳定标识，格式为 `<source_type>/<source_file>`。 |
| `source`         | `string`       | 是     | 与 `ProseChunk.source` 对齐：见下表。           |
| `source_file`    | `string`       | 是     | 原始文件名，不含路径。                             |
| `source_url`     | `string        | null` | 否                                       |
| `source_type`    | `string`       | 是     | 见 3.4 节。                                |
| `since_version`  | `string        | null` | 否                                       |
| `confidence`     | `string        | null` | 否                                       |
| `title`          | `string        | null` | 否                                       |
| `keep`           | `bool`         | 是     | 文档级开关；`false` 则 chunker 整篇跳过。           |
| `match_tokens`   | `list[string]` | 否     | 文档级检索挂钩，合并到 chunk 的 `related_symbols`。  |
| `blocks`         | `list[Block]`  | 是     | 有序块列表。                                  |


`source` 取值：


| 类型       | `source`                                       |
| -------- | ---------------------------------------------- |
| A 官方升级指南 | `official_prose`、`official_prose_3to4_shader`  |
| B、C 官方文档 | `official_doc`                                 |
| D 官方博客   | `official_blog`                                |
| E GitHub | `github_pr`、`github_issue`、`github_discussion` |
| F、G 社区   | `community_prose`                              |




### 3.3 块字段


| 字段             | 类型             | 必填    | 说明                                                           |
| -------------- | -------------- | ----- | ------------------------------------------------------------ |
| `block_id`     | `string`       | 是     | 文档内稳定 id，格式 `b0001`、`b0002`...                               |
| `type`         | `string`       | 是     | `heading`、`paragraph`、`code`、`list`、`admonition`、`quote` 之一。 |
| `text`         | `string`       | 是     | 纯文本。                                                         |
| `heading_path` | `list[string]` | 是     | 从文档顶到当前小节的标题路径。                                              |
| `level`        | `int           | null` | heading 必填                                                   |
| `language`     | `string        | null` | code 可选                                                      |
| `subtype`      | `string        | null` | 可选                                                           |




### 3.4 `source_type` 枚举

```text
rst
html_sphinx
html_blog
github_pr
github_issue
github_discussion
community_blog
gist
legacy_prose_jsonl
```

`legacy_prose_jsonl` 仅用于 chunker lift 类型 A 后的内存表示。

### 3.5 IR 示例

```json
{
  "schema_version": 1,
  "doc_id": "rst/gdscript_basics.rst",
  "source": "official_doc",
  "source_file": "gdscript_basics.rst",
  "source_url": "https://github.com/godotengine/godot-docs/blob/master/tutorials/scripting/gdscript/gdscript_basics.rst",
  "source_type": "rst",
  "since_version": "4.0",
  "confidence": "verified",
  "title": "GDScript reference",
  "keep": true,
  "match_tokens": ["await", "@onready", "@export"],
  "blocks": [
    {
      "block_id": "b0001",
      "type": "heading",
      "level": 2,
      "text": "Annotations",
      "heading_path": ["GDScript reference"]
    },
    {
      "block_id": "b0002",
      "type": "paragraph",
      "text": "Annotations are extra information that can be given to the interpreter...",
      "heading_path": ["GDScript reference", "Annotations"]
    },
    {
      "block_id": "b0003",
      "type": "code",
      "language": "gdscript",
      "text": "@export var speed := 0",
      "heading_path": ["GDScript reference", "Annotations"]
    },
    {
      "block_id": "b0004",
      "type": "admonition",
      "subtype": "warning",
      "text": "Using @onready and @export together on the same variable triggers ONREADY_WITH_EXPORT.",
      "heading_path": ["GDScript reference", "Annotations"]
    }
  ]
}
```



### 3.6 类型 A 的退化 IR lift

类型 A 已有 `*.prose.jsonl`，不另写 `.ir.json`。chunker 把每一行 lift 成内存中的退化 `ProseDocument`：

```json
{
  "schema_version": 1,
  "doc_id": "legacy_prose_jsonl/upgrading_to_godot_4.1.rst#Upgrading from Godot 4.0 to Godot 4.1/...",
  "source": "official_prose",
  "source_file": "upgrading_to_godot_4.1.rst",
  "source_url": null,
  "source_type": "legacy_prose_jsonl",
  "since_version": "4.1",
  "confidence": "verified",
  "title": null,
  "keep": true,
  "match_tokens": [],
  "blocks": [
    {
      "block_id": "b0001",
      "type": "paragraph",
      "text": "...",
      "heading_path": ["Upgrading from Godot 4.0 to Godot 4.1", "..."]
    }
  ]
}
```

---



## 4. 公共组件（`rag/build/prose_preprocessing_util/`）

所有 process 脚本共享这些纯函数/模型。每个文件只负责一件事，不耦合 I/O。

### 4.1 `ir.py`

- `ProseBlock`：块级 Pydantic 模型。
- `ProseDocument`：文档级 Pydantic 模型。
- `read_ir(path: Path) -> ProseDocument`
- `write_ir(doc: ProseDocument, path: Path)`
- `make_doc_id(source_type: str, source_file: str) -> str`



### 4.2 `filters.py`

- `length_filter(blocks, min_chars: int) -> list[Block]` 重要：并非所有类型的文档都要用这个filter，比如官方升级文档rst的prose本来段落就很短，不可使用filter，请你检查7个类型文档的处理方式，谁用filter，谁不能用都取决于原来的处理管线设计。
- `boilerplate_filter(blocks, patterns: list[re.Pattern]) -> list[Block]`
- `signature_density_filter(blocks, threshold: float = 0.5) -> list[Block]`：用于类型 C 丢弃 API 签名表。
- `github_noise_filter(blocks) -> list[Block]`：用于类型 E 丢弃 +1/Thanks/纯表情。



### 4.3 `selectors.py`

每个 selector 返回三元组 `(keep, drop, uncertain)`：

- `heading_allowlist_select(blocks, allowlist: list[str])`
- `heading_denylist_select(blocks, denylist: list[str])`
- `keyword_allowlist_select(blocks, keywords: list[str])`
- `topic_map_select(blocks, topic_map: dict)`
- `maintainer_select(blocks, logins: list[str])`：类型 E 用。
- `combine_select(*results) -> (keep, drop, uncertain)`：合并多个 selector 结果，denylist 优先，allowlist 次之，其余 uncertain。



### 4.4 `parsers.py`

统一格式解析入口：

- `parse_rst(rst_text: str, source_path: str) -> list[Block]`：复用 `parse_upgrading_docs.py` 的 docutils 逻辑。
- `parse_html(html_text: str, profile: str) -> list[Block]`：`profile` 可选 `sphinx`、`godot_blog`、`community`。
- `parse_markdown(md_text: str) -> list[Block]`：用于 GitHub API Markdown。



### 4.5 `heading_path.py`

- `HeadingPath`：维护标题栈，支持 `enter(title, level)` / `exit(level)` / `current()`。



### 4.6 `review_queue.py`

- `ReviewItem`：Pydantic 模型。
- `append_queue(path: Path, items: list[ReviewItem])`
- `read_queue(path: Path) -> list[ReviewItem]`

`ReviewItem` 字段：

```json
{
  "doc_id": "community_blog/await-coroutine-basics.html",
  "block_id": "b0012",
  "text": "...截断文本...",
  "proposed": "keep",
  "channel": "heuristic",
  "reason": "keyword_allowlist: await+_process"
}
```

---



## 5. Scanner：`scan_tier_b_raw.py`



### 5.1 职责

1. 遍历 `rag/vault/tier_b_prose/_raw/` 下 7 个文件夹。
2. 对每个文件按扩展名选择 parser：
  - `.rst` → `parsers.parse_rst`
  - `.html` → `parsers.parse_html`
  - `.md` 或无扩展名 → `parsers.parse_markdown`
3. 输出到 `after_preprocess/<bucket>/<source_file>.blocks.jsonl`，每行一个 block 草稿。
4. **不读 policy、不做筛选、不写 IR**。



### 5.2 HTML profile 选择规则


| 来源桶                             | profile      |
| ------------------------------- | ------------ |
| official_html_doc               | `sphinx`     |
| official_blog                   | `godot_blog` |
| community_blog / community_gist | `community`  |

GitHub 三桶是 `.md`（`download_github_api.py` 写入），scan 走 `parse_markdown`，不使用 HTML profile。




### 5.3 block 草稿字段

与 IR 块字段一致，但此时 `type` 为原始结构类型，`heading_path` 已建好。

---



## 6. 七个桶的脚本特性



### 6.1 通用约定

- 输入：`after_preprocess/<bucket>/<file>.blocks.jsonl`
- 输出：`ir/<bucket>/<file>.ir.json`（F/G 除外，只输出 review_queue）
- 每个脚本都可以通过环境变量 `TIER_B_REVIEW_MODE=1` 进入 review 模式：把 uncertain/候选块打印到 stdout，不写入 IR。



### 6.2 类型 A：官方升级指南

- **无独立 process 脚本**。
- **输入**：`_raw/official_upgrading_guide/*.prose.jsonl`
- **处理**：`chunk_and_embed.py` 直接 lift，不生成 `.ir.json`。
- **Human-in-the-loop**：无。



### 6.3 类型 B：官方 GDScript rst

- **脚本**：`process_official_gdscript_doc.py`
- **输入**：`after_preprocess/official_gdscript_doc/*.blocks.jsonl`
- **处理流程**：
  1. `length_filter(blocks, 40)`
  2. `boilerplate_filter(blocks, patterns)`
  3. `heading_denylist_select` → drop
  4. `heading_allowlist_select` + `keyword_allowlist_select` → keep
  5. 其余 → uncertain，默认 drop
- **输出**：`ir/official_gdscript_doc/*.ir.json`
- **Human-in-the-loop**：
  - 默认自动运行，不需要中断。
  - 若设置 `TIER_B_REVIEW_MODE=1`，脚本会打印被 drop/uncertain 的块，维护者检查关键段落（`await` 语义、`Annotations`、`ONREADY_WITH_EXPORT`）是否被误丢，然后调整 `policy/heading_allowlist.yaml` 或 `policy/keyword_allowlist.yaml` 重跑。



### 6.4 类型 C：官方 Sphinx HTML

- **脚本**：`process_official_html_doc.py`
- **输入**：`after_preprocess/official_html_doc/*.blocks.jsonl`
- **处理流程**：
  1. `length_filter(blocks, 80)`
  2. `boilerplate_filter`
  3. `signature_density_filter(blocks, 0.5)` → drop 签名表
  4. 剩余描述段 + code → keep
- **输出**：`ir/official_html_doc/*.ir.json`
- **Human-in-the-loop**：
  - 默认自动运行。
  - review 模式下抽查是否与 A 层 `rules.db` 重复到没有增量语义。



### 6.5 类型 D：官方博客

- **脚本**：`process_official_blog.py`
- **输入**：`after_preprocess/official_blog/*.blocks.jsonl`
- **处理流程**：
  1. `length_filter(blocks, 80)`
  2. `boilerplate_filter`
  3. `topic_map_select` 命中 OS/RPC/Tween 等主题 → keep
  4. heading 命中 "下一步" / "发布计划" → drop
  5. 动机段连续 paragraph → keep
- **输出**：`ir/official_blog/*.ir.json`
- **Human-in-the-loop**：
  - 默认自动运行。
  - review 模式下核验设计动机段是否被切断。



### 6.6 类型 E：GitHub PR / Issue / Discussion

- **脚本**：`process_github.py`
- **输入**：`after_preprocess/github_pr/`、`github_issue/`、`github_discussion/`
- **处理流程**：
  1. `github_noise_filter`：丢弃 +1、Thanks、Any update?、纯表情
  2. `length_filter(blocks, 20)`
  3. 作者 ∈ `policy/maintainer_logins.yaml` → keep
  4. 含代码围栏 → keep
  5. 其余 → drop
- **输出**：`ir/github_pr/*.ir.json`、`ir/github_issue/*.ir.json`、`ir/github_discussion/*.ir.json`
- **Human-in-the-loop**：
  - 默认自动运行。
  - review 模式下抽查 keep 集合是否包含 README 关心的设计论述。
- **注意**：`_raw/github_*/*.md` 是 GitHub API 正文（由 `download_github_api.py` 写入，heading 为 `body by <login>` / `comment by <login>`）。`scan_tier_b_raw.py` 按 `.md` 解析；`process_github.py` **只读** `after_preprocess` jsonl，运行时不再打 API。刷新原文时重新跑下载脚本，不要去抓 github.com HTML。



### 6.7 类型 F：社区博客

- **脚本**：`process_community.py`
- **输入**：`after_preprocess/community_blog/*.blocks.jsonl`
- **处理流程**：
  1. `length_filter(blocks, 80)`
  2. `boilerplate_filter`
  3. 启发式筛选：块内包含反引号 API、代码块、`error`、`Godot 4`、`not working`、`migration`、`silent` → 作为候选
  4. **不写 IR**，候选块写入 `review_queue.jsonl`
- **输出**：`review_queue.jsonl`（追加）
- **Human-in-the-loop**（核心）：
  - 脚本运行后自动停止并提示："请查看 review_queue.jsonl，挑选需要入库的段落并写入 curation/.yaml，然后运行 compile_curation.py"。
  - 维护者读 queue，把真正有价值的段落写成 `curation/<stem>.yaml`。
  - 运行 `compile_curation.py` 后生成 `ir/community_blog/*.ir.json`。



### 6.8 类型 G：社区 Gist

- **脚本**：`process_community.py`（与 F 共用同一脚本，按桶名区分）
- **输入**：`after_preprocess/community_gist/*.blocks.jsonl`
- **处理流程**：与 F 相同，启发式筛选候选。
- **输出**：`review_queue.jsonl`（追加）
- **Human-in-the-loop**：
  - 与 F 相同。
  - gist 内容跨多个主题，建议按主题拆成多份 `curation/<stem>.<topic>.yaml`，每份标注 `match_tokens`。

---



## 7. Curation 编译：`compile_curation.py`



### 7.1 输入

`curation/<stem>.yaml`，字段：

```yaml
source_file: await-coroutine-basics.html
source_url: https://uhiyama-lab.com/en/notes/godot/await-coroutine-basics/
source: community_prose
source_type: community_blog
since_version: "4.0"
confidence: needs_review
title: Await coroutine basics
match_tokens: ["yield", "await", "_process"]
excerpts:
  - heading_path: ["Migrating from Godot 3's yield"]
    text: |
      ...
    code: |
      func _process(delta):
          await something
    language: gdscript
```



### 7.2 输出

`ir/community_blog/<stem>.ir.json` 或 `ir/community_gist/<stem>.<topic>.ir.json`

### 7.3 规则

- 每个 excerpt 生成 1 个 `paragraph` block + 可选 1 个 `code` block。
- `keep = true`，`confidence = needs_review`。
- 文档级 `match_tokens` 合并到每个 chunk 的 `related_symbols`。

---



## 8. Chunker 与 Embedding 策略

`chunk_and_embed.py` 负责把 Document IR 切成检索单元，并在 build 阶段生成 embedding、写入 LanceDB。它内部拆为两个子阶段：

1. **Chunk 阶段**：IR → `ProseChunk` 列表。
2. **Embed 阶段**：`ProseChunk` → 向量 → `artifacts/corpus.lance`。

### 8.1 设计原则

- **Build 阶段完成 embedding**：向量在 build 时生成，运行时只查 LanceDB，不再加载 embedding 模型。
- **LanceDB 同表存储向量 + 文本**：`corpus.lance` 中同时保存 `vector`、`text`、`heading_path`、`since_version_code` 等全部字段，检索时一次查询直接返回完整 chunk，不需要回查 IR 文件或 SQLite。
- **模型固定**：使用 `BAAI/bge-small-en-v1.5`，输出 384 维向量，最大输入 512 token。
- **中英文说明**：bge-small-en-v1.5 是英文模型；Agent 调用 retrieve 时建议优先使用英文符号名 / 报错原文（通过 `RetrievalQuery.symbols` 和 `error_text`），以获得最佳召回。中文 `query_text` 也能召回英文文档，但效果弱于英文 query。

### 8.2 Chunk 阶段输入

1. `ir/<bucket>/*.ir.json` 中所有 `keep=true` 的文档。
2. `_raw/official_upgrading_guide/*.prose.jsonl` lift 后的退化 IR。

### 8.3 Chunk 阶段算法

1. 跳过 `type=heading`。
2. 按 `heading_path` 装箱，同小节内连续 block 合并。
3. `code` 不跨 chunk；说明段 + 紧随 code 尽量同块。
4. 目标 320–400 token，硬上限 480 token（embedding 输入 = heading 前缀 + body，必须 < 512）。
5. 小节超上限时在 block 边界切；单个 block 仍超限才硬切。
6. 官方源 body < 20 字符丢弃，社区源 < 80 字符丢弃。
7. `ProseChunk.text` 只含 body，不含 heading 前缀。

### 8.4 Embedding 阶段

#### 8.4.1 模型与库

- **模型**：`BAAI/bge-small-en-v1.5`（384 维，max 512 tokens）。
- **库**：`fastembed`（轻量，默认支持 bge-small-en-v1.5，仅在 build 依赖组中安装）。
- **tokenizer**：使用模型配套的 tokenizer 计算 token 数；实现阶段可用 `fastembed` 的 `TextEmbedding` API。

#### 8.4.2 Embedding 文本构造

```text
embedding_text = " > ".join(heading_path) + "\n\n" + body
```

- `heading_path` 为空时只 embed body。
- `body` 是 chunk 内各 block 用 `\n\n` 拼接后的纯文本。

#### 8.4.3 `corpus.lance` 表 Schema

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 稳定 chunk id。 |
| `vector` | vector(384) | bge-small-en-v1.5 生成的向量。 |
| `text` | string | chunk body（不含 heading 前缀），Agent 展示用。 |
| `heading_path` | list<string> | 该 chunk 的标题路径。 |
| `since_version` | string \| null | 文档级版本。 |
| `since_version_code` | int | 版本编码，LanceDB 前置过滤用。 |
| `related_symbols` | list<string> | body 反引号符号 ∪ 文档级 `match_tokens`。 |
| `source` | string | `official_prose` / `official_doc` / `official_blog` / `github_*` / `community_prose`。 |
| `source_file` | string | 原始文件名。 |
| `source_url` | string \| null | 可引用 URL。 |

#### 8.4.4 写入流程

1. 创建/打开 `artifacts/corpus.lance`。
2. 若表已存在，按 `id` 去重或整表重建（build 脚本默认重建，保证幂等）。
3. 使用 LanceDB 的 `add()` 写入 PyArrow 表或 Pydantic 列表。
4. 可选：创建 IVF_PQ 向量索引和 FTS（全文）索引，加速 hybrid search。

### 8.5 关于父子块（parent-child chunking）

**当前规模不采用父子块**。原因：

- 语料仅 21 个文件，按 `heading_path` 装箱后的 chunk 已经包含完整上下文。
- 迁移知识的核心是“说明 + 代码示例”，通常在同一小节内，不需要额外父块补充上下文。
- 父子块增加复杂度；若未来扩展到 200+ 文件且发现召回 chunk 过短、上下文不足，再引入不迟。

若未来引入，建议：
- 子块：按 paragraph/code 小粒度，用于向量检索。
- 父块：按 heading_path 整节，用于返回给 Agent 的上下文。

---



## 9. 典型工作流（维护者视角）



### 9.1 第一次初始化

```bash
# 1. 归一化所有源文件
uv run python rag/build/scan_tier_b_raw.py

# 2. 处理官方源（A–E），直接生成 IR
uv run python rag/build/process_official_gdscript_doc.py
uv run python rag/build/process_official_html_doc.py
uv run python rag/build/process_official_blog.py
uv run python rag/build/process_github.py

# 3. 处理社区源，只生成 review queue
uv run python rag/build/process_community.py

# 4. 人工查看 review_queue.jsonl，写 curation/*.yaml
# ...

# 5. 编译 curation 成 IR
uv run python rag/build/compile_curation.py

# 6. 切块
uv run python rag/build/chunk_and_embed.py
```



### 9.2 新增一个官方源

1. 放到 `_raw/<对应桶>/`。
2. 运行 `scan_tier_b_raw.py`。
3. 运行对应 `process_*.py`。
4. 运行 `chunk_and_embed.py`。



### 9.3 新增一个社区源

1. 放到 `_raw/community_blog/` 或 `_raw/community_gist/`。
2. 运行 `scan_tier_b_raw.py`。
3. 运行 `process_community.py`，生成 queue。
4. 人工写 `curation/<stem>.yaml`。
5. 运行 `compile_curation.py`。
6. 运行 `chunk_and_embed.py`。

---



## 10. 验收口径

- `_raw/` 下 21 个文件全部在 `after_preprocess/` 有对应的 `.blocks.jsonl`。
- A–E 类每个源文件都有 `ir/<bucket>/<file>.ir.json`。
- F/G 类没有直接写 IR，只生成 `review_queue.jsonl`。
- `chunk_and_embed.py` 产出的 chunk 无 nav/footer/签名表/纯 +1。
- `await` / `ONREADY_WITH_EXPORT` / Tween 动机 / RPC 静默失败等关键知识点完整保留。
- 同一 IR 连续两次 chunk 的 id 集合相同。

