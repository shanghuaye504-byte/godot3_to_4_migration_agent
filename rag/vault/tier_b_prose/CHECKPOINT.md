# Checkpoint：B 层预处理 / chunking 第一次真实跑通到哪一步

> 写于 2026-08-28。这不是设计协议（协议仍是 [CHUNKING.md](CHUNKING.md)），只记录**这一次真实跑流水线**的落点：哪些产物已经在磁盘上、哪些必须你来做、以及 `policy/` 里那些白名单/黑名单到底是谁写的。
>
> 一句话：**预处理和切块都真实跑过了；embedding 没写成 LanceDB；社区语料还停在人工队列。policy 文件不是空的，也不是你写的——实现流水线时按 CHUNKING.md / README 的例子填了一份启动种子，请当你自己的草稿来改，不要当成已经审过的规则。**

---

## 1. 有没有真实跑过？

有。不是只跑 pytest。在 `rag/` 下用项目自己的 `.venv`（Python 3.11.15）按 [CHUNKING.md](CHUNKING.md) §9.1 的顺序执行过：

```text
scan_tier_b_raw.py
process_official_gdscript_doc.py
process_official_html_doc.py
process_official_blog.py
TIER_B_SKIP_GITHUB_API=1  process_github.py
process_community.py
compile_curation.py
TIER_B_SKIP_EMBED=1       chunk_and_embed.py
```

另外还试过一次**不跳过 embed** 的 `chunk_and_embed.py`：切块阶段同样得到 178 个 chunk，随后 `fastembed` 去 Hugging Face 拉 `BAAI/bge-small-en-v1.5`，被代理拦成 `403 Forbidden`，因此 **`rag/artifacts/corpus.lance` 仍然只有空的 `.gitkeep`，没有向量表。**

当时的开关：

| 开关 | 当时的值 | 影响 |
|------|----------|------|
| `TIER_B_SKIP_GITHUB_API` | `1` | GitHub 桶没有打 API，只用 `_raw/github_*` 的 HTML 快照 |
| `TIER_B_REVIEW_MODE` | 未设置 | B–E 直接写 IR，没有把 drop/uncertain 打到 stdout 给你看 |
| `TIER_B_SKIP_EMBED` | 验收跑用了 `1`；另一次去掉后因 403 失败 | 切块做了，向量没落盘 |

---

## 2. 工作流完成度（对照 CHUNKING.md 四阶段）

```text
_raw/  ──scan──►  after_preprocess/  ──process_*──►  ir/  ──chunk──►  chunks  ──embed──►  corpus.lance
                         │                              ▲
                    F/G only                    compile_curation.py
                         ▼                              │
              review_queue.jsonl  ──你写 YAML──►  curation/
```

| 阶段 | 脚本 | 状态 | 磁盘上现在有什么 |
|------|------|------|------------------|
| 0. 源文件 | （此前下载） | 完成 | `_raw/` 21 个异构源 + 8 份 type A `*.prose.jsonl` |
| 1. 扫描归一化 | `scan_tier_b_raw.py` | **完成** | `after_preprocess/` 下 21 个 `.blocks.jsonl`（与 `_raw` 一一对应，不含 type A） |
| 2a. 官方 / GitHub 筛选 | `process_official_*` + `process_github.py` | **完成（自动路径）** | `ir/` 下 **13** 份 `.ir.json`（B+C+D+E，见下表） |
| 2b. 社区启发式 | `process_community.py` | **完成到队列为止** | `rag/build/intermediate/prose_review_queue.jsonl` **114 行**；**没有** `ir/community_*` |
| 3. 编译 curation | `compile_curation.py` | **空转** | `curation/` 目录存在但是空的，脚本打印 `no curation YAML files` |
| 4a. 切块 | `chunk_and_embed.py` 的 chunk 阶段 | **完成（内存/日志，未单独落盘）** | 日志：`chunked 178 chunks from 74 docs`（61 份 type A 退化文档 + 13 份 IR） |
| 4b. 向量入库 | 同脚本 embed 阶段 | **未完成** | `artifacts/corpus.lance/` 仍只有 `.gitkeep` |

### 2.1 已写出的 IR（13 份，全部 `keep=true`）

| 桶（CHUNKING 类型） | 文件 | blocks |
|---------------------|------|--------|
| official_gdscript_doc（B） | `gdscript_basics.rst.ir.json` | 69 |
| official_gdscript_doc（B） | `gdscript_styleguide.rst.ir.json` | 15 |
| official_gdscript_doc（B） | `signals_step_by_step.rst.ir.json` | 70 |
| official_html_doc（C） | `class_editorplugin.html.ir.json` | 134 |
| official_html_doc（C） | `class_fileaccess.html.ir.json` | 132 |
| official_html_doc（C） | `using_character_body_2d.html.ir.json` | 66 |
| official_blog（D） | `core-refactoring-progress-report-2.html.ir.json` | 22 |
| official_blog（D） | `multiplayer-changes-godot-4-0-report-2.html.ir.json` | 42 |
| github_pr（E） | `godot_pull_41794.html.ir.json` | 108 |
| github_pr（E） | `godot_pull_65271.html.ir.json` | 33 |
| github_issue（E） | `godot-docs_issue_5577.html.ir.json` | 11 |
| github_issue（E） | `godot-docs_issue_6265.html.ir.json` | 4 |
| github_discussion（E） | `godot-proposals_discussion_6192.html.ir.json` | 8 |

抽查过：`gdscript_basics` 的 IR 里仍有 `ONREADY_WITH_EXPORT` 那段。RST 解析会跳过 simple table（避免 keyword 表整表漏进 B 层）。

### 2.2 已知不够干净、但这次没停下来等人的地方

这些**不是** CHUNKING.md 规定必须打断的 HITL，但第一次自动跑完之后建议你看一眼：

- **GitHub 走的是 HTML 快照，不是 API。** `godot-docs_issue_6265.html` 本身是 GitHub 的 “Uh oh! Please reload” 错误页。脚本后来加了「保留 opening post、丢掉 chrome」，所以 IR 有 4 个 block，质量取决于这份坏快照里还剩什么。有网时应去掉 `TIER_B_SKIP_GITHUB_API` 重跑 `process_github.py`。
- **PR #41794 留了 108 个 block。** opening post + 代码块 + maintainer 评论叠在一起，比「只留设计动机」宽得多，可能偏吵。
- **没有开 `TIER_B_REVIEW_MODE=1`。** 类型 B 里 heading/keyword 都没打中的块被默认 drop，没打印给你核对。CHUNKING.md §6.3 点名要人工确认的 `await` / Annotations / `ONREADY_WITH_EXPORT`，目前只靠抽查 IR 文本，不是完整 review 日志。
- **切块结果没有单独的 jsonl 文件。** 178 这个数字只出现在脚本 stdout 里；不 embed 就不写 LanceDB，所以你现在不能打开一个 chunk 清单文件逐条看。要落盘必须先让 embed 成功，或以后给 chunker 加 `--dump-chunks`（这次没加）。

---

## 3. 哪些必须 Human-in-the-loop

按协议，**真正挡住入库的只有 F/G**。其余是「建议复核」，流水线不会停。

### 3.1 必须你做（否则社区语料进不了检索库）

1. 打开 `rag/build/intermediate/prose_review_queue.jsonl`（114 条启发式候选：反引号 API、代码块、`error` / `Godot 4` / `not working` / `migration` / `silent` 等）。
2. 对照 [README.md](README.md) 表 2.2「补充源」列：社区文章的价值是那几句行为差异，不是整篇教程。
3. 把你要留的段落写成 `curation/<stem>.yaml`（gist 建议按主题拆成多份，带 `match_tokens`）。格式见 CHUNKING.md §7.1。
4. 再跑 `compile_curation.py`，才会出现 `ir/community_blog/`、`ir/community_gist/`。
5. 然后再跑 `chunk_and_embed.py`。

现在 `curation/` 是空的，所以上面第 4 步上次是 no-op。**队列 ≠ 已入库。** 启发式只是帮你缩小阅读范围，默认不会 `keep=true` 写 IR。

### 3.2 建议你做（不挡自动化，但影响信噪比）

| 动作 | 为什么 |
|------|--------|
| 读 / 改 `policy/*.yaml` 和 `boilerplate_patterns.txt` | 见下一节：现在是启动种子，不是你的规则 |
| `TIER_B_REVIEW_MODE=1` 重跑类型 B | 确认 uncertain 默认 drop 没有误杀关键段 |
| 有网时让 `process_github.py` 走 API | 修好 6265 那种坏 HTML；Discussion 6192 的 OP 作者不在 maintainer 名单里，目前只靠 opening-post 规则才留了 8 块 |
| 抽查 IR 是否和 A 层 `rules.db` 重复到没有增量 | CHUNKING.md §6.4 写给类型 C 的 |
| 能访问 Hugging Face 时跑完整 `chunk_and_embed.py` | 否则 B 层检索没有 `corpus.lance` |

### 3.3 不需要 HITL

- **类型 A**（`_raw/official_upgrading_guide/*.prose.jsonl`）：A 层编译时已经切过，chunker 直接 lift，无 process 脚本。
- **类型 C/D 的默认自动路径**：签名表密度、topic map、长度下限都在脚本里硬编码或读 policy，跑完即写 IR。

---

## 4. 白名单 / 黑名单：不是空的，也不是你写的

你没有自己维护过这些文件。实现 `process_*.py` 时，**没有把列表留空**——空名单会让类型 B 几乎全部变成 uncertain → 默认 drop，第一次跑会得到空 IR，没法验收。所以按 CHUNKING.md 点名的章节名、README 里的十条知识点、以及几位常见 Godot 维护者登录名，**填了一份启动种子**。

请把它当成「为了第一次能跑起来的草稿」，**不要当成已经人工审过的政策。** 改这些 YAML 再重跑对应 `process_*.py` 即可，不必改 Python。

### 4.1 `policy/` 里现在有什么（启动种子全文）

路径：`rag/vault/tier_b_prose/policy/`。

**`heading_allowlist.yaml`**（类型 B：命中则 keep）

```yaml
allowlist:
  - Annotations
  - Coroutines
  - Signals
  - Await
```

来源：CHUNKING.md §6.3 要求盯住的章节，加上 GDScript 手册里和迁移最相关的几个 heading 子串。

**`heading_denylist.yaml`**（类型 B 直接 drop；类型 D 也会读，并再叠一层脚本内硬编码）

```yaml
denylist:
  - History
  - "Next steps"
  - "Release plan"
```

来源：CHUNKING.md §6.5 写了 heading 命中「下一步 / 发布计划」则 drop；英文写法一并放进 YAML。`History` 来自 GDScript 参考里会把历史章节整节丢掉的常见需求。

**`keyword_allowlist.yaml`**（类型 B：正文命中则 keep）

```yaml
keywords:
  - deprecated
  - breaking
  - await
  - "@rpc"
  - "@export"
  - "@onready"
  - "@tool"
  - yield
```

来源：README 表 2.2 / 2.3 的迁移关键词，不是从语料里统计出来的。

**`topic_map.yaml`**（类型 D：官方博客必须留的主题）

```yaml
topics:
  - OS
  - DisplayServer
  - Time
  - Engine
  - RPC
  - "@rpc"
  - Tween
  - create_tween
```

来源：README 里那两篇官方博客要讲的事（OS 拆分、RPC），外加 Tween 作为相关主题。不是从 HTML 里自动抽取的。

**`maintainer_logins.yaml`**（类型 E：这些作者的评论自动 keep）

```yaml
logins:
  - akien-mga
  - reduz
  - Calinou
```

来源：Godot 仓库里最常见的官方账号，**没有**对照这 5 个 HTML 快照里实际出现过谁。Discussion 6192 的楼主如果不在这三人里，不会走 maintainer 通道（这次靠 opening post 才留下正文）。

**`boilerplate_patterns.txt`**（几乎所有 process 脚本都会用，一行一条正则）

```text
Last updated on
Edit this page on GitHub
Sign up for free to join this conversation
Was this page helpful\?
Table of contents
On this page
```

来源：Sphinx / GitHub 页面上最常见的页脚和 chrome 短句。覆盖面很窄，社区博客的 newsletter / Subscribe 未必能匹配到。

### 4.2 写在 Python 里、不在 YAML 里的规则

改行为要动脚本，不是改 policy。这次跑的时候它们已经生效：

| 位置 | 规则 |
|------|------|
| 各 `process_*.py` | 长度下限：B=40，C/D/F/G=80，E=20（字符，见 CHUNKING.md） |
| `process_official_html_doc.py` | `signature_density_filter(..., 0.5)` 丢掉 API 签名表 |
| `process_official_blog.py` 的 `_EXTRA_DENY` | 再 drop：`下一步` / `发布计划` / `Future` / `Next steps` / `Release plan` |
| `process_official_gdscript_doc.py` | heading/keyword 都未命中 → **uncertain → 默认 drop** |
| `process_github.py` | 丢掉 GitHub chrome（Uh oh、Please reload、Sign in…）；`github_noise_filter` 丢掉 +1 / Thanks；**保留 opening post 整节**；保留 `type=code` |
| `process_community.py` 的 `_HEURISTIC_KEYWORDS` | 只决定谁进 **review queue**，不写 IR |
| `parsers.py` | RST 跳过表格；Sphinx 跳过 `classref-reftable-group` 和方法表 id |
| `chunk_and_embed.py` | 官方 chunk body &lt; 20 字符丢、社区 &lt; 80 丢；heading 不进 body；code 不跨 chunk；上限约 480 token |

如果名单当时是空的，代码不会崩溃：selector 得到空 keep/空 deny，类型 B 会几乎全部 uncertain 后丢掉。这次没有走那条路。

### 4.3 你如果要「从自己的规则重新跑」

1. 编辑 `policy/`（或先清空列表，接受类型 B IR 可能变空）。
2. 重跑对应的 `process_*.py`（会覆盖 `ir/` 里同名文件）。
3. 社区桶：改启发式或直接不管 queue、以你手写的 `curation/*.yaml` 为准。
4. 再跑 `chunk_and_embed.py`。

`after_preprocess/` 只有在 parser 变了时才需要重跑 `scan_tier_b_raw.py`。只改白名单不必重新 parse HTML。

---

## 5. 建议的下一步（按必须程度）

1. **HITL（必须，若要社区知识入库）**：读 114 条 queue → 写 `curation/*.yaml` → `compile_curation.py`。
2. **审种子政策（强烈建议）**：打开 `policy/`，删掉你不认可的条目、补上你真正在意的 heading/关键词/维护者。
3. **GitHub（建议）**：有网时不设 `TIER_B_SKIP_GITHUB_API`，重跑 `process_github.py`。
4. **Embedding（必须，若要 B 层向量检索）**：能访问 Hugging Face 时在 `rag/` 下执行 `.venv/bin/python build/chunk_and_embed.py`，确认 `artifacts/corpus.lance` 不再只有 `.gitkeep`。

单元测试（33 条、不碰真实 vault）的说明在仓库的 [`docs/pytest_tier_b_walkthrough.md`](../../../docs/pytest_tier_b_walkthrough.md)，和这份 checkpoint 不是同一件事。

---

## 6. 重跑指导（抽样结论 + 关跳过开关 + 空 policy + GitHub API）

下面按 [CHUNKING.md](CHUNKING.md) 的 **类型 A–G 七个桶**写（E 对应 `github_pr` / `github_issue` / `github_discussion` 三个文件夹）。抽样对象是当前磁盘上的 13 份 IR、8 份 type A `*.prose.jsonl`、以及 114 条 review queue，不是凭记忆。

抽样时每个已写入 IR 的文件都看了：`after_preprocess` → IR 的保留比例、`heading_path` 列表、关键知识点是否还在、以及明显噪音（chrome、签名行、SEO 目录、docutils `:ref:`）。

### 6.1 抽样一览

| 桶 | 文件 | 扫描块 → IR 块 | 抽样结论（一句话） |
|----|------|----------------|--------------------|
| A 官方升级指南 | 8 份 `*.prose.jsonl` | 无 IR；61 行退化文档 | 结构正常，无 HITL；缺主文 `upgrading_to_godot_4.rst` 的散文（只有 shader 切块） |
| B GDScript rst | basics 459→69；styleguide 202→15；signals 70→**70** | 关键段在，但白名单太宽 + 英文词误伤 |
| C Sphinx HTML | editorplugin 225→134；fileaccess 239→132；characterbody 73→66 | 教程还行；类参考仍大量「方法/属性描述」 |
| D 官方博客 | OS 文 34→22；RPC 文 52→42 | 设计动机在；同父标题下的相邻小节被顺带留下 |
| E GitHub | 41794: 211→108；65271: 54→33；5577: 25→11；6265: 18→4；6192: 26→8 | HTML 快照质量差不齐；走 API 值得 |
| F 社区博客 | 无 IR；queue 103 条（7 篇） | 队列里混着 SEO「What You'll Learn」 |
| G 社区 gist | 无 IR；queue 11 条 | 按协议本应人工拆主题，现在只有启发式碎片 |

### 6.2 分桶：这次 IR / 队列里实际出现的问题

#### 类型 A · `official_upgrading_guide`（无 process 脚本）

- 8 份 jsonl 每行一段，最短也 ≥70 字符，没有「空壳段落」。
- chunker 会把**每一行** lift 成一份退化 IR，所以日志里的「74 docs」= 61 行 type A + 13 份 B–E IR，不是 8 个文件。
- **缺口**：没有 `upgrading_to_godot_4.rst.prose.jsonl`（3→4 主文），只有 `upgrading_to_godot_4.rst.updating_shaders.prose.jsonl`。这是 A 层当时的切分产物，不是这次 B 层脚本丢的。若你希望 3→4 主文的说明性段落也进 B 层，需要回到 A 层 `parse_upgrading_docs.py` / `clean_prose_jsonl.py` 的出口，**不要**在 B 层再 parse 一遍 rst。
- 重跑 B 层时这一桶**不用动**，chunker 会自动 lift。

#### 类型 B · `official_gdscript_doc`

关键知识点抽查：`ONREADY_WITH_EXPORT`、`@onready`/`@export`、`await`、Annotations 都在 `gdscript_basics` IR 里。`History` 已被 denylist 丢掉。

出现的问题：

1. **`signals_step_by_step.rst` 70/70 整篇留下。** `heading_allowlist` 里的 `Signals` 是**子串匹配**，标题路径 `Using signals` 全部命中。这不是 parser 坏了，是种子白名单太粗。
2. **英文词误伤。** `Packed arrays` 那段留下，是因为正文有 *may yield improvements*，命中了 keyword `yield`。`Comments` 里 comment-marker 列表含 `DEPRECATED`，命中 `deprecated`。
3. **`match_tokens` 被 docutils 角色污染。** basics 的 tokens 里出现 `GDScript class reference <class_@GDScript>`、`:` 这种 `:ref:` 残渣；signals 那篇更明显（`Unknown interpreted` / `No role` 仍在正文里）。
4. **styleguide 只剩 15 块**是预期内的「uncertain 默认 drop」：没打中 Annotations/Signals/await 等就丢掉。若你觉得风格指南里 `@onready var ...: set =` 那种链式写法该留，要靠加 keyword/heading，而不是怪 drop 逻辑。

重跑前请你审 `heading_allowlist.yaml` / `keyword_allowlist.yaml`：避免过短的 `Signals`、`Await`；考虑要不要把 `yield` 改成更严的匹配（当前实现是大小写不敏感子串，改匹配规则要动 `selectors.py`，不在「只改 YAML」范围内）。然后用 `TIER_B_REVIEW_MODE=1` 看 drop/uncertain 列表，确认 `ONREADY_WITH_EXPORT` 仍在 keep 里。

#### 类型 C · `official_html_doc`

- `using_character_body_2d.html`：73→66，`velocity` / `move_and_slide` 都在，这一份最接近「该留的教程」。
- `class_fileaccess.html` / `class_editorplugin.html`：仍各有 130+ 块。扫描阶段已经跳过方法表 DOM，但 **Property Descriptions / Method Descriptions** 下的逐方法说明（含 `FileAccess create_temp (mode_flags: ...) static` 这种签名行）靠 `signature_density_filter(0.5)` 没滤干净。CHUNKING.md §6.4 说类参考只留描述性文字；当前 IR 更像「精简过的 API 手册」，会和 A 层 `extension_api` 大量重复。
- `EditorPlugin` 的 Description 里能抽到 `super` 相关说明，这条知识点还在。

重跑时：默认仍自动写 IR。建议你开 `TIER_B_REVIEW_MODE=1` 看 drop 列表；若仍太吵，需要改 parser 跳过的 section id、或把「Method Descriptions」加进某种 denylist（**现在类型 C 不读 `heading_denylist.yaml`**，只改 YAML 救不了类参考）。这是抽样发现的实现缺口，不是你没填政策。

#### 类型 D · `official_blog`

- OS 文：`OS / DisplayServer split` 动机段在；因为「同一 `heading_path` 的段落跟着 keep」，父路径只有 `Core refactoring` 时，**Window node / Embedded mode** 等相邻小节也被留下。
- RPC 文：`master`/`puppet` → `@rpc` 的设计论述在，42/52 几乎整篇。对这篇来说整篇都相关，问题不大；但 `topic_map` 里若留下过短的 `OS`、`Time`、`Engine`，别的博客也可能被拖进来。
- 页脚 Donate/patron 这次没进 IR。

重跑前审 `topic_map.yaml`。类型 D 也读 `heading_denylist.yaml`，并与脚本内 `_EXTRA_DENY`（下一步/发布计划/Future…）合并。

#### 类型 E · GitHub（三个文件夹、一个脚本）

| 文件 | 问题 |
|------|------|
| `godot_pull_41794.html` | HTML 把 **PR 作者 KoBeWi 整段描述**当成第一级 heading。opening-post 规则于是留下整份 PR 正文（设计上合理），再加 reduz 评论和所有 `code` 块 → 108 块。信噪比一般，但「Tweens are no longer nodes / fire and forget」在。 |
| `godot_pull_65271.html` | 维护者评论 + FileAccess/`close()` 在；HTML 评论树仍然偏碎。 |
| `godot-docs_issue_5577.html` | OP 里旧 `connect` vs Callable 对照是好的；IR 末尾多了一个 **Metadata** heading（GitHub chrome）。 |
| `godot-docs_issue_6265.html` | **`_raw` HTML 是损坏快照**：页面里有 `Uh oh!` / `Please reload`，正文主要来自 JSON-LD/meta。IR 只剩 grammar 链接 + 「convert setget to set and get」两句，**没有社区补充源里说的 setter 触发时机差异**（那本来就在社区博客，不在这个 issue）。评论数在页面结构化数据里是 0，API 也补不出长讨论。 |
| `godot-proposals_discussion_6192.html` | 只有楼主反对 `@onready` 的论述。README 写的「官方回应为什么用 @ 前缀」**不在这份 HTML IR 里**。这是最需要 API/GraphQL 的一份。 |

HTML 解析还把作者 login 塞进 `subtype`/heading（41794 的 heading 是 `KoBeWi`、`reduz`），和 API 路径下 `body by {login}` / `comment by {login}` 的结构不一致。所以 **HTML 跑出来的 IR 不能当 API 跑出来的基准**。

#### 类型 F · `community_blog`

没有 IR，这是协议规定的。114 条里 103 条来自 7 篇博客。抽样：`await-coroutine-basics` 的 `b0003` 是 **What You'll Learn** 目录，启发式因为含 `await`/`Godot 4` 进了队列。队列是候选人，不是已入库；你写 `curation/*.yaml` 时丢掉这类 SEO 即可。

#### 类型 G · `community_gist`

11 条候选，对 WolfgangSenff 那份跨 Tween / EditorPlugin / RectangleShape2D 的长笔记来说**太粗也太少**。CHUNKING.md §6.8：按主题拆成多份 `curation/<stem>.<topic>.yaml` 并标注 `match_tokens`。不要指望这 11 条自动变成好 IR。

### 6.3 空 policy：代码不会崩，但有的桶会得到空 IR

上次那句「名单为空会把全部 block 抛弃」需要收窄：**Python 不会因为列表为空而异常退出**；YAML **文件本身**必须在（`process_*.py` 会 `read_text`，删掉文件才是崩溃）。

空列表时 selector 的行为是：allow/topic/maintainer 一个都 keep 不了；denylist 一个都 drop 不了；`combine_select` 之后其余全是 **uncertain**。

| policy 文件 | 谁读 | 列表全空时 | 重跑时能否留空 |
|-------------|------|------------|----------------|
| `heading_allowlist.yaml` | 仅类型 B | 不靠 heading keep | **可以留空，但 B 必须另有非空 `keyword_allowlist`**，否则 B 的 uncertain 默认 drop → **IR 块列表为空** |
| `keyword_allowlist.yaml` | 仅类型 B | 不靠正文关键词 keep | 同上：与 heading 白名单 **至少一份非空** |
| `heading_denylist.yaml` | 类型 B；类型 D 再叠 `_EXTRA_DENY` | 不按标题丢 History/Next steps | **可以留空**（只是更吵）。D 的中文「下一步/发布计划」仍会被脚本硬编码丢掉 |
| `boilerplate_patterns.txt` | B/C/D/F/G | 不按页脚正则丢 chrome | **可以留空**（只留 `#` 注释也行）。`load_boilerplate_patterns` 对空文件返回 `[]` |
| `topic_map.yaml` | 仅类型 D | 主题 keep 为零，同路径连带 keep 也没有种子 | **不能留空**：D 会写出几乎没有正文的 IR（或空 blocks） |
| `maintainer_logins.yaml` | 仅类型 E | 不按作者 keep 评论 | **可以留空**：E 仍会保留 opening post + 所有 code 块 |

类型 C **完全不读** allow/deny/keyword/topic/maintainer，只读 boilerplate + 硬编码的长度/签名密度。所以你把 B 的白名单留空，C 不受影响。

类型 F/G 不读白名单；启发式关键词写在 `process_community.py` 的 `_HEURISTIC_KEYWORDS` 里。空 boilerplate 只让更多页脚进 queue，**不会**让社区自动写 IR。

实操建议：

- 文件都留着，用 `allowlist: []` 这种显式空列表，不要删文件。
- 你审核后：**B 保留你真正要的 heading/关键词（至少一类有内容）**；**D 的 `topics` 至少留这篇博客在乎的符号**（例如 `DisplayServer`、`@rpc`）；denylist / boilerplate / maintainer 可以先空着，用 review 日志再补。
- 若 B 两边都空，脚本仍会退出码 0 并写出 `keep=true` 但 `blocks: []` 的 JSON——看起来「跑通了」，chunker 不会从空文档掏出检索单元。这是上次说「全部抛弃」的真正含义，不是 traceback。

### 6.4 GitHub：vault 已换成 API Markdown

`_raw/github_*` 现在是 `download_github_api.py` 写出的 `.md`（`body by` / `comment by`），HTML 快照已删除。`process_github.py` **运行时不再打 API**，只滤 scan 产出的 jsonl。刷新原文：`gh auth login` 后在 `rag/` 下跑 `.venv/bin/python build/download_github_api.py`，再 `scan` + `process_github`。

Discussion 6192 的 Markdown 已含 dalexeev 对 `@onready` / 注解语义的回复；6265 是干净短正文，没有 Uh oh。

### 6.5 按 CHUNKING.md 重跑（GitHub 不必再 export token 给 process）

上次为了跑通打开/维持的跳过：

| 开关 | 上次 | 这次 |
|------|------|------|
| `TIER_B_SKIP_GITHUB_API` | `=1` | **已删除该开关**；process 不联网 |
| `TIER_B_REVIEW_MODE` | 未设（直接写 IR，等于跳过抽查打印） | 官方/GitHub **先** `=1` 看日志，审完 policy **再**不设，才能写 IR |
| `TIER_B_SKIP_EMBED` | 验收时 `=1` | 最终入库 **不要设**（仍访问不了 Hugging Face 就先不要跑第 6 步） |

注意：`TIER_B_REVIEW_MODE=1` 时 `process_file` 返回 `None`，**不会覆盖 `ir/`**。所以严格流程是两段：先 review，再正式写。

在 `rag/` 下、用 `.venv`（不要在仓库根目录 `uv run`）：

```bash
cd rag
# 0. 你先审 policy/（见 §6.3），文件留着，空列表用 []

# 1. 格式归一化（GitHub 现为 .md，必须 scan 一次才能出 jsonl）
.venv/bin/python build/scan_tier_b_raw.py

# 2a. HITL 抽查：只打印 keep/drop/uncertain，不写 IR
TIER_B_REVIEW_MODE=1 .venv/bin/python build/process_official_gdscript_doc.py
TIER_B_REVIEW_MODE=1 .venv/bin/python build/process_official_html_doc.py
TIER_B_REVIEW_MODE=1 .venv/bin/python build/process_official_blog.py
TIER_B_REVIEW_MODE=1 .venv/bin/python build/process_github.py
# 根据日志改 policy/，重复 2a 直到你接受 keep 集合

# 2b. 正式写 B–E 的 IR
.venv/bin/python build/process_official_gdscript_doc.py
.venv/bin/python build/process_official_html_doc.py
.venv/bin/python build/process_official_blog.py
.venv/bin/python build/process_github.py

# 3. 社区：只生成 queue，不写 IR
.venv/bin/python build/process_community.py
# 你读 rag/build/intermediate/prose_review_queue.jsonl
# 按 README 表 2.2 把要留的句子写入 vault/tier_b_prose/curation/*.yaml
# gist 按主题拆文件

# 4. 编译人工 YAML → ir/community_*
.venv/bin/python build/compile_curation.py

# 5. 切块 + embedding → artifacts/corpus.lance
.venv/bin/python build/chunk_and_embed.py
```

`compile_curation.py` 在 `curation/` 仍为空时会 no-op 并提示；这是正常的，不是失败。社区知识只有 YAML 写进去之后才会进 13 份以外的 IR。

第 5 步仍会下载 `BAAI/bge-small-en-v1.5`。网络或代理 403 时，不要设回 `TIER_B_SKIP_EMBED` 来「假装完成」——跳过 embed 就不会写 LanceDB。等 HF 能访问再跑这一条即可；前面的 IR / curation 已经留在磁盘上。

