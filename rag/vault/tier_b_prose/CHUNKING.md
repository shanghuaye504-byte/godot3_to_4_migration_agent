# B 层 Prose 预处理工作手册

> 本手册是 `rag/vault/tier_b_prose/` 的**唯一本地协议**。它指导维护者如何把 `_raw/` 下 21 个异构源文件预处理成统一的 Document IR，再交给 `chunk_prose.py` 装箱、`embed_prose.py` 写入 LanceDB。
>
> 设计目标：小规模（≈21 文件）下极度简化，不引入工作流引擎、LLM 层或统一编排器；同时保留 IR 统一出口和 chunker 统一性，未来扩展到 200 文件时只需逐个桶加规则，不需要重写架构。
>
> 参考文档：
>
> - 语料清单与来源说明：[README.md](README.md)
> - HTML/RST/Markdown 提取示例：[docs/prose_preprocessing_guide.md](../../../docs/prose_preprocessing_guide.md)
> - 检索侧契约：[rag/retriever/README.md](../../retriever/README.md)（入口）、[docs/tier-b.md](../../retriever/docs/tier-b.md)（查询配对）
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
    ir --> chunker["chunk_prose.py"]
    chunker --> jsonl["artifacts/chunks/strategy/chunks.jsonl"]
    jsonl --> embedder["embed_prose.py"]
    embedder --> lance["artifacts/corpora/strategy/corpus.lance"]

    proc -.->|F/G only| queue["review_queue.jsonl"]
    queue -.->|human| curation["curation/<stem>.yaml"]
    curation -.->|compile_curation.py| ir
```




| 阶段             | 做什么                                              | 入口脚本                  | 产物                                              |
| -------------- | ------------------------------------------------ | --------------------- | ----------------------------------------------- |
| 1. 格式归一化       | 按扩展名把 rst/html/md 解析成带 `heading_path` 的 block 草稿 | `scan_tier_b_raw.py`  | `after_preprocess/<bucket>/<file>.blocks.jsonl` |
| 2. 桶级处理        | 每个桶独立 filter/select；官方源直接写 IR；社区源生成 review queue | `process_<bucket>.py` | `ir/*.ir.json` 或 `review_queue.jsonl`           |
| 3. 编译 Curation | 把人工确认后的 curation YAML 编译成 IR                     | `compile_curation.py` | `ir/community_*/*.ir.json`                      |
| 4a. 切块         | 读全部 IR + lift 类型 A，按策略装箱                         | `chunk_prose.py`      | `artifacts/chunks/<id>/chunks.jsonl`            |
| 4b. Embedding  | 读 jsonl，生成向量，写入独立 LanceDB                         | `embed_prose.py`      | `artifacts/corpora/<id>/corpus.lance`           |




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
│   ├── review_queue.py                # review_queue.jsonl 读写
│   ├── chunker.py                     # IR → ProseChunk 装箱
│   └── bge.py                         # bge WordPiece 计数 + TextEmbedding 单例
│
├── scan_tier_b_raw.py                 # 阶段 1：扫描 + 格式归一化
├── download_github_api.py             # 类型 E：API → _raw/*.md
├── process_official_gdscript_doc.py   # 类型 B
├── process_official_html_doc.py       # 类型 C
├── process_official_blog.py           # 类型 D
├── process_github.py                  # 类型 E（只滤 jsonl）
├── process_community.py               # 类型 F/G
├── compile_curation.py                # 阶段 3：YAML → IR
├── chunk_prose.py                     # 阶段 4a：IR → chunks.jsonl
├── embed_prose.py                     # 阶段 4b：jsonl → corpus.lance
└── chunk_and_embed.py                 # 薄封装：默认策略先 chunk 再 embed
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



### 4.7 `chunker.py`

- `ChunkConfig`：切块参数（mode / chunk_size / overlap / max_tokens / target_tokens / 字数下限 / code 绑定）。
- `chunk_documents(docs, config=..., token_counter=...) -> list[ProseChunk]`：按 heading_path 装箱。生产由 `chunk_prose.py` 传入 `bge_token_count`。
- `approx_token_count`：正则近似，**只给单测**。
- `lift_prose_jsonl(path)` / `load_ir_documents(ir_dir)` / `type_a_paths(tier_b_dir)`：给 `chunk_prose.py` 用的装载函数。
- `split_code_at_functions(text)`：按顶层 `func` / `class` / `enum` 切代码。

算法细节见第 8 节。纯函数，不写盘；落盘由 `chunk_prose.py` 负责。

### 4.8 `bge.py`

- `get_text_embedding()`：懒加载 `TextEmbedding("BAAI/bge-small-en-v1.5")`，缓存目录读 `FASTEMBED_CACHE_PATH`。
- `bge_token_count(text)`：同一套 WordPiece，给切块装箱和 embed 侧 512 截断共用。

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
- **处理**：`chunk_prose.py` 直接 lift，不生成 `.ir.json`。
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

切块和向量写入是两个脚本，中间落盘一份可复现的 `chunks.jsonl`，方便用不同参数生成多份 LanceDB 做召回对比。

```text
IR + 类型 A *.prose.jsonl
  → chunk_prose.py
  → artifacts/chunks/<strategy_id>/chunks.jsonl
     artifacts/chunks/<strategy_id>/manifest.json
  → embed_prose.py
  → artifacts/corpora/<strategy_id>/corpus.lance
```

默认 `strategy_id=default`。`embed_prose.py` 在写入 `corpora/default/` 之后，会再镜像一份到 `artifacts/corpus.lance`，兼容旧路径。其它 strategy 不碰这条路径。

`chunk_and_embed.py` 只是薄封装：先跑默认（或传入的）chunk，再 embed。`--skip-embed` / `TIER_B_SKIP_EMBED=1` 仍可只切块。对比实验请直接调两个脚本。

### 8.1 设计原则

- **切块与 embedding 分离**：换 overlap / chunk-size 时不必重跑 IR。
- **Build 阶段完成 embedding**：运行时只查 LanceDB。
- **LanceDB 同表存储向量 + 文本**：检索一次返回完整 chunk。
- **模型固定**：`BAAI/bge-small-en-v1.5`，384 维，最大输入 512 token。切块与建库共用 WordPiece；建库 `passage_embed`，检索 `query_embed`。
- **中英文说明**：检索时优先英文符号名 / 报错原文。

### 8.2 Chunk 阶段输入

1. `ir/<bucket>/*.ir.json` 中所有 `keep=true` 的文档。
2. `_raw/official_upgrading_guide/*.prose.jsonl` lift 后的退化 IR。

### 8.3 可调参数（第一次跑用默认值）

在 `rag/` 下：

```bash
uv run python build/chunk_prose.py --strategy-id default
```

| 参数 | 默认 | 含义 |
| --- | --- | --- |
| `--mode` | `heading` | 按 `heading_path` 装箱。`fixed` 时对纯 prose 再按 `--chunk-size` 开窗。 |
| `--chunk-size` | `0` | 固定窗 token 数；0 表示不按固定长度切。 |
| `--overlap` | `0` | 相邻 chunk 重叠的 prose token；0 表示不 overlap。Overlap 在 code 边界停止。 |
| `--max-tokens` | `480` | embedding 文本（heading 前缀 + body）硬上限。 |
| `--target-tokens` | `360` | 软目标：尽量装满，未到上限不主动切；过短尾块可并入上一块。 |
| `--min-chars-official` | `20` | 官方源过短 body 丢弃。 |
| `--min-chars-community` | `80` | 社区源过短 body 丢弃。 |
| `--code-attach` | `preceding` | 代码与紧邻前文说明绑成一捆。 |
| `--code-split` | `function` | 超限时按 `func` / `class` / `enum` 边界切，不在函数体中间切。 |

`manifest.json` 记下上述参数和 `chunk_count`，换策略时只改 CLI 和 `--strategy-id`。

### 8.4 Chunk 阶段算法

1. 跳过 `type=heading`。
2. 按 `heading_path` 分组。
3. 组内打 bundle：连续 prose 累积，遇到 `code` 则「前文 + 该 code」成一捆。
4. 按 bundle 贪心装箱（软目标 360，硬上限 480）。
5. 单捆超限：先切 prose，整段 code 跟最后一块能放下的说明走；仍超限才按函数边界切 code。单个函数仍超 480 时整函数单独成块并 warning，避免从函数中间切开。
6. `--overlap > 0` 且同小节多块时，后一块前缀叠前一块末尾 overlap 个 token 的 prose。
7. `--mode fixed --chunk-size N`：只对纯 prose bundle 开窗；含 code 的 bundle 仍走原子路径。
8. `ProseChunk.text` 只含 body。

### 8.5 Embedding 阶段

```bash
uv run python build/embed_prose.py --strategy-id default
```

- 模型：`BAAI/bge-small-en-v1.5`（`fastembed`，仅 build 依赖组）。
- 建库 API：`passage_embed(embedding_text)`。检索必须 `query_embed(query)`，禁止 `embed()`。
- `embedding_text = " > ".join(heading_path) + "\n\n" + body`。
- 切块计数与 512 截断都用 `bge_token_count`（与模型同一套 WordPiece）。
- 若单函数块仍超过模型 512 token，只截断送进模型，**不改** `chunks.jsonl` / Lance 的 `text`。
- 表 schema 与原先 §8.4.3 相同（`id` / `vector` / `text` / `heading_path` / `since_version` / `since_version_code` / `related_symbols` / `source` / `source_file` / `source_url`）。
- 每个 strategy 目录整表重建，保证幂等。
- 细节见 **§11**。

### 8.6 关于父子块（parent-child chunking）

**当前规模不采用父子块**。按 `heading_path` 装箱后的 chunk 已含「说明 + 代码」。若未来语料扩大且召回过短，再引入。

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

# 6. 切块（默认策略；需 build 组 + FASTEMBED_CACHE_PATH，用 bge WordPiece）
uv run python rag/build/chunk_prose.py --strategy-id default

# 7. Embedding（passage_embed；缓存已有则可离线）
uv run python rag/build/embed_prose.py --strategy-id default
```



### 9.2 新增一个官方源

1. 放到 `_raw/<对应桶>/`。
2. 运行 `scan_tier_b_raw.py`。
3. 运行对应 `process_*.py`。
4. 运行 `chunk_prose.py`，需要向量时再运行 `embed_prose.py`。



### 9.3 新增一个社区源

1. 放到 `_raw/community_blog/` 或 `_raw/community_gist/`。
2. 运行 `scan_tier_b_raw.py`。
3. 运行 `process_community.py`，生成 queue。
4. 人工写 `curation/<stem>.yaml`。
5. 运行 `compile_curation.py`。
6. 运行 `chunk_prose.py`，需要向量时再运行 `embed_prose.py`。

---



## 10. 验收口径

- `_raw/` 下 21 个文件全部在 `after_preprocess/` 有对应的 `.blocks.jsonl`。
- A–E 类每个源文件都有 `ir/<bucket>/<file>.ir.json`。
- F/G 类没有直接写 IR，只生成 `review_queue.jsonl`。
- `chunk_prose.py` 产出的 chunk 无 nav/footer/签名表/纯 +1。
- `await` / `ONREADY_WITH_EXPORT` / Tween 动机 / RPC 静默失败等关键知识点完整保留。
- 同一 IR、同一策略连续两次 chunk 的 id 集合相同。

---



## 11. Embedding：tokenizer、passage_embed 与 LanceDB

切块策略见 §8；CLI 见 `chunk_prose.py` / `embed_prose.py` 模块 docstring。检索配对见 [retriever/docs/tier-b.md](../../retriever/docs/tier-b.md)。

### 11.1 切块与模型用同一套 WordPiece

| 环节 | tokenizer |
| --- | --- |
| 装箱（`chunk_prose.py` → `bge_token_count`） | bge-small-en-v1.5 WordPiece（`TextEmbedding.token_count`） |
| 送进模型前的 512 截断（`embed_prose._truncate_for_embed`） | 同上 |
| `passage_embed` 真正编码 | 同一 `TextEmbedding` 单例 |

`approx_token_count`（正则）**只给 pytest**，生产路径缺 `fastembed` 时直接失败，不回退正则。

装箱硬上限仍是 **480**（低于模型 512）。单个函数仍超 480 时整函数成块并 warning；embed 侧若 WordPiece > 512 只截断**模型输入**，`chunks.jsonl` 与 Lance 的 `text` 保持全文。

切块脚本依赖 `[dependency-groups] build`。无参数 `uv sync` **不会**装 `fastembed`，还会卸掉已经装上的 build 组。本机开发：

```bash
cd rag && uv sync --group build --group dev
export FASTEMBED_CACHE_PATH="$HOME/.cache/fastembed"
```

### 11.2 建库 `passage_embed`，检索 `query_embed`

LanceDB **不内嵌模型**，只存 384 维向量 + chunk 字段。建库和检索都必须用 `BAAI/bge-small-en-v1.5`。换模型或换 API = 整表作废，必须重嵌。

| API | 用途 | 本仓库 |
| --- | --- | --- |
| `passage_embed()` | 文档/段落 | **建库走这条**（`embed_prose.embed_chunks`） |
| `query_embed()` | 查询（报错原文 / 符号） | 检索必须走这条；`tier_b.py` 尚未实现 |
| `embed()` | 通用编码 | **禁止**对本 corpus 使用，不能与上面两条混用 |

建库送进模型的是 `embedding_text`：`" > ".join(heading_path) + "\n\n" + body`。检索时对 **query 字符串** 做 `query_embed`，不要给 query 拼 heading 前缀。

`tier_b.py` 仍是空 stub。接上时：读 `artifacts/corpora/<strategy_id>/`（或兼容路径 `artifacts/corpus.lance`），用同一个 `get_text_embedding()`，**只**对 query 调 `query_embed`。不要在 Lance 里再配一套不同的 embedding function。

### 11.3 缓存与第一次下载

模型公开，**不需要** `HF_TOKEN`。fastembed 读 `FASTEMBED_CACHE_PATH`（未设置则落到临时目录，不要依赖它）。本机约定：

```bash
export FASTEMBED_CACHE_PATH="$HOME/.cache/fastembed"
```

缓存里已有 `models--qdrant--bge-small-en-v1.5-onnx-q` 和 `.onnx` 时，`HF_HUB_OFFLINE=1` 可完全离线切块和建库。首次没有缓存才需要访问 Hugging Face（或 `HF_ENDPOINT=https://hf-mirror.com`）。

```bash
cd rag
export FASTEMBED_CACHE_PATH="$HOME/.cache/fastembed"
uv run python build/chunk_prose.py --strategy-id default
uv run python build/embed_prose.py --strategy-id default
```

成功标志：`artifacts/chunks/default/chunks.jsonl` 与 `corpora/default/corpus.lance` 行数一致，向量 384 维；`artifacts/corpus.lance` 被 default 镜像覆盖。
