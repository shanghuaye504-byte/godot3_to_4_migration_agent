# 这一轮实际做了什么：给 B 层预处理写 pytest，以及为什么要这么写

> 这篇文档不是协议说明书。协议在 [`rag/vault/tier_b_prose/CHUNKING.md`](../rag/vault/tier_b_prose/CHUNKING.md)，检索契约在 [`rag/retriever/docs/`](../rag/retriever/docs/README.md)，包怎么用在 [`rag/README.md`](../rag/README.md)。
>
> 这篇是给「从来没自己搭过 pytest、但想把这件事学会」的人看的：测试文件为什么长那样、pytest 是怎么找到它们的、`tmp_path` / `monkeypatch` / `conftest.py` 分别在干什么、以及这一轮实际敲了哪些命令、得到了什么结果。把它当课堂笔记，不当权威设计。
>
> 代码实现本身不在这里展开。下面只在需要解释「测的是哪一层」时点一下文件名。

---

## 0. 先把任务本身说清楚

用户这一轮要的是：把 `CHUNKING.md` 里规划的 **Tier B prose 预处理 + chunking** 全部落地，**不要改 A 层已有代码**，架子和注释已经写好、按原架构填空。填完之后跑测试。另外希望顺便学一下 pytest：测试模块是怎么生成的、流程是什么。

所以这一轮有两条线：

1. **主线**：`scan → process_* → compile_curation → chunk_and_embed`，公共能力在 `rag/build/prose_preprocessing_util/`。
2. **顺便**：在 `rag/test/` 下新增三个 pytest 模块，用它们锁住主线里「最容易写错、又最不该每次打开 1.4 MB HTML 才能发现」的那些规则。`rag/eval/` 留给离线召回评测，不进默认 pytest 套件。

pytest 不是生产流水线的一部分。worker 镜像不会跑这些测试。它只是本机开发时的护栏：改了 filter / selector / chunker，几秒钟就能知道有没有把 `@export` 短代码块滤掉、有没有把 API 方法表当散文塞进去。

---

## 1. pytest 到底是什么（从零）

Python 自带 `unittest`，但现在大多数项目用 **pytest**。你只需要记住三件事：

1. **一个函数就是一条用例。** 文件名以 `test_` 开头（或 `_test` 结尾），函数名以 `test_` 开头。pytest 会把它们全部收集起来，一条一条跑。
2. **断言就是 `assert`。** 不用写 `self.assertEqual(...)`。左边不等于右边时，pytest 会把两边的值打印出来。
3. **失败立刻停这一条，继续下一条。** 33 条里坏了 1 条，你会看到 32 passed / 1 failed，而不是整场测试中断。

一个最小的测试文件长这样：

```python
def test_one_plus_one():
    assert 1 + 1 == 2
```

跑它：

```bash
cd rag
.venv/bin/pytest test/test_something.py -v
```

`-v` 是 verbose：每条用例的名字都会打出来，而不是只显示一个点。第一次学的时候一定加 `-v`，否则你看不见「到底跑了哪些函数」。

pytest **不会**自己去「猜你想测什么」。你必须写函数、写 `assert`。它负责的是：找到这些函数、给它们准备临时目录、隔离环境变量、把失败信息打印得好看。

---

## 2. 测试为什么放在 `rag/test/`，评测为什么在 `rag/eval/`

两件事不要混在一个目录里：

| 目录 | 打不打进 wheel | 干什么 |
|------|----------------|--------|
| `rag/retriever/` | 打进去 | worker 运行时检索 |
| `rag/build/` | 不打进去 | 本机编译脚本（含 `prose_preprocessing_util`） |
| `rag/test/` | 不打进去 | pytest：工程正确性（filter / chunker / `rules.db` 不变量） |
| `rag/eval/` | 不打进去 | 离线召回评测（评测集、难例、消融），**不是** pytest 套件 |
| `rag/vault/`、`rag/artifacts/` | 不打进去 | 源数据和编译产物 |

`rag/pyproject.toml` 里已经写了：

```toml
[tool.pytest.ini_options]
testpaths = ["test"]
```

意思是：你在 `rag/` 目录下敲 `pytest`（不带路径），它只去 `test/` 里找测试，不会扫 `eval/`，也不会把 `build/` 里的脚本误当成测试文件。

`dev` 依赖组里有 `pytest>=8.0`。本机一次性装齐：

```bash
cd rag
uv sync --group build --group dev
```

`build` 组带 docutils / beautifulsoup4 / fastembed 这些编译脚本要用的库；`dev` 组带 pytest 和 ruff。worker 镜像用 `uv sync --no-default-groups`，两边都不会装。

---

## 3. 最容易踩的坑：必须用 `rag/.venv`，不要在仓库根目录 `uv run`

这一轮第一次跑测试时，如果在**仓库根目录**敲 `uv run pytest`，会落到系统 Python 3.13，而且 pytest 的 `rootdir` 变成整个 workspace，找不到 `rag/pyproject.toml` 里的 `testpaths`。

正确做法永远是：**先 `cd rag`，再用这个包自己的虚拟环境。**

```bash
cd "/Users/yy_catmax/workspace/Godot Workspace/godot3_to_4_migration_agent/rag"
.venv/bin/pytest test/test_prose_preprocessing_util.py \
                 test/test_tier_b_processors.py \
                 test/test_chunk_and_embed.py \
                 -v --tb=short
```

为什么写三个文件名，而不是直接 `pytest`？因为 `test/` 里还有一份**更早的** `test_build_artifacts.py`，测的是 A 层 `rules.db` 的不变量。那份测试这一轮**故意没改**。它依赖 `build_all.sh` 已经跑过、`artifacts/rules.db` 存在。把它和 B 层的纯函数测试混在一起，失败原因会搅在一块。学 pytest 的时候，先只跑你刚写的那三个模块。

`--tb=short` 是 traceback 短模式：失败时只打关键几行，不会把半个调用栈糊在屏幕上。

---

## 4. `conftest.py`：测试启动前那 10 行

`rag/test/conftest.py` 是 pytest 的约定文件名。只要它躺在测试目录里，**每一场测试开始前**都会先执行它，你不用 `import` 它。

这一轮它只做一件事：把 `rag/build/` 塞进 `sys.path`。

```python
BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
if str(BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(BUILD_DIR))
```

为什么需要？因为项目有两种 import 世界：

| import | 谁提供 | 打不打进 wheel |
|--------|--------|----------------|
| `from rag.retriever.schemas import ProseChunk` | 可编辑安装的 `rag` 包（`uv sync` 之后） | 打进去 |
| `from prose_preprocessing_util.filters import length_filter` | `rag/build/prose_preprocessing_util/`，和 `process_*.py` 平级 | **不打进去** |
| `import chunk_and_embed as ce` | `rag/build/chunk_and_embed.py` 本身 | **不打进去** |

编译脚本自己也是「把 `build/` 加进 `sys.path`，然后 `from prose_preprocessing_util...`」。测试必须用同一套规则，否则你在测试里 `import` 成功、在脚本里失败（或反过来），那种 bug 极难查。

`conftest.py` 还有一个副作用：它是**整场测试共享的夹具箱**。这一轮没在里面定义 fixture（后面会讲 fixture 是什么），只用来改路径。以后如果很多测试都需要「一份假的 policy YAML」，可以写在这里，写一次、所有 `test/test_*.py` 都能用。

---

## 5. 三个测试文件怎么拆：按「失败时你想打开哪个文件」

不要做一个 `test_everything.py`。拆文件的原则是：**这条断言失败了，你希望立刻知道去改哪一层。**

| 文件 | 测什么 | 失败时打开 |
|------|--------|------------|
| `test/test_prose_preprocessing_util.py` | heading 栈、IR 读写、四个 filter、五个 selector、RST/HTML/MD 解析、review queue | `rag/build/prose_preprocessing_util/` |
| `test/test_tier_b_processors.py` | 各桶 `process_file` 的 keep/drop；社区桶只写 queue 不写 IR；curation YAML → IR | 对应的 `process_*.py` / `compile_curation.py` |
| `test/test_chunk_and_embed.py` | type A 的 jsonl 提升、装箱、代码块不切断、官方 20 / 社区 80 字下限、`keep=false` 跳过、chunk id 稳定、硬切不超过 token 上限、`ProseChunk` 自动填 `since_version_code` | `chunk_and_embed.py` 和 `rag/retriever/schemas.py` |

这一轮一共 **33 条**。名字都尽量写成「主语 + 行为 + 对象」，pytest `-v` 打出来就是一句人话，例如：

```
test_length_filter_keeps_short_code_and_headings
test_process_github_keeps_opening_post
test_chunker_does_not_split_code_across_chunks
```

以后你改了 GitHub 的 keep 规则，只跑一个文件甚至一条都可以：

```bash
.venv/bin/pytest test/test_tier_b_processors.py -v
.venv/bin/pytest test/test_tier_b_processors.py::test_process_github_keeps_opening_post -v
```

`文件::函数名` 是 pytest 的选择语法。改一小处时不要整场 33 条都跑——不是因为慢（整场 0.2 秒），而是因为失败列表短，你的注意力才准。

---

## 6. 写一条测试的固定套路：Arrange / Act / Assert

几乎每一条都是这三步，业界叫 **AAA**：

1. **Arrange**：准备输入。内存里拼一个假 HTML、假 RST，或者在临时目录写一个假 jsonl。
2. **Act**：调用**一个**被测函数。`parse_html(...)`、`process_file(...)`、`chunk_documents(...)`。
3. **Assert**：只断言你真正在意的那一两件事。

以 Sphinx 解析为例（缩写自真实用例）：

```python
def test_parse_html_sphinx_skips_method_tables() -> None:
    # Arrange：最小 HTML，含一段 Description + 一张 Methods 表
    html = """
    <div role="main">
      <div itemprop="articleBody">
        <section id="description">
          <p>This class can be used to permanently store data...</p>
        </section>
        <section class="classref-reftable-group" id="methods">
          <table><tr><td>void</td><td>close()</td></tr></table>
        </section>
      </div>
    </div>
    """
    # Act
    blocks = parse_html(html, "sphinx")
    texts = " ".join(b.text for b in blocks)
    # Assert：散文在，方法表不在
    assert "permanently store data" in texts
    assert "close()" not in texts
```

为什么不直接拿 `class_fileaccess.html`（两百多 KB）当输入？因为那份文件里同时有 Description、教程、方法表、枚举表。测试失败时你不知道是 selector 坏了、parser 坏了，还是官方又改了 HTML 结构。**最小夹具把「一条规则」从「整份文档」里抠出来。**

例外：`test_parse_real_gdscript_basics_keeps_onready` 会读 vault 里真正的 `gdscript_basics.rst`。这是有意的回归锚：RST 解析曾经把 keyword 表连同 docutils 的 `:ref:` 报错一起吞进去，这条用例锁住「Annotations 里的 `ONREADY_WITH_EXPORT` 必须还在」。文件不存在就直接 `return`（等于跳过），避免有人只 clone 了代码、没带 vault 时整场变红。

---

## 7. pytest 送给你的两个参数：`tmp_path` 和 `monkeypatch`

函数参数叫 **fixture**（夹具）。你在参数列表里写出名字，pytest 在调用前把对象造好传进来。这一轮只用了两个内置的。

### 7.1 `tmp_path`：每条用例一个扔掉的目录

pytest 会在系统临时目录下建一个只属于**这一条**用例的空文件夹。用例结束就删。

典型用法：测「把 IR 写到磁盘再读回来还是不是同一个对象」。

```python
def test_make_doc_id_and_roundtrip(tmp_path) -> None:
    path = tmp_path / "gdscript_basics.rst.ir.json"
    write_ir(doc, path)
    loaded = read_ir(path)
    assert loaded.doc_id == doc.doc_id
```

**绝对不要**在测试里往 `rag/vault/` 或 `rag/build/intermediate/` 写东西。`process_community.main()` 会删掉再重建 review queue；如果你的测试调用了 `main()` 还指向真实路径，下一次你打开 queue 会发现自己的 HITL 记录没了。所以社区桶那条测试做了两件事：用 `tmp_path` 当假的预处理目录，再用 `monkeypatch` 把脚本里的常量指过去。

### 7.2 `monkeypatch`：改环境变量、改模块里的路径，测完自动还原

`monkeypatch.setenv("TIER_B_SKIP_GITHUB_API", "1")` 让 GitHub 处理器不要打 GitHub API。真实流水线在没网、或者 HTML 快照已经够用时也用同一个开关。测试里设了，用例结束 pytest 会把环境变量改回去，不会污染下一条。

更关键的是 **`monkeypatch.setattr`**：把模块级常量换成临时路径。

```python
def test_process_community_writes_queue_not_ir(tmp_path, monkeypatch) -> None:
    queue = tmp_path / "prose_review_queue.jsonl"
    monkeypatch.setattr(process_community, "QUEUE_PATH", queue)
    monkeypatch.setattr(process_community, "PREPROCESS_DIR", tmp_path)
    # ...在 tmp_path/community_blog/ 写下假 jsonl...
    n = process_community.process_bucket("community_blog")
    assert n >= 1
    assert queue.is_file()
    assert not list(tmp_path.rglob("*.ir.json"))  # 社区桶禁止自动写 IR
```

`compile_curation` 那条同样把 `CURATION_DIR` / `OUTPUT_DIR` 指到 `tmp_path`，用一份手写的 YAML 确认「段落 + 代码块能编成 IR」，而不去碰还是空的 `vault/tier_b_prose/curation/`。

记住一句：**测试可以 import 生产模块，但不可以让生产模块往真实产物目录写。** 路径全部 patch 掉。

---

## 8. 为什么单元测试不下载 embedding 模型

`chunk_and_embed.py` 内部其实是两段：

1. **Chunk**：IR → `ProseChunk` 列表。纯函数，不联网，测这个。
2. **Embed**：把文本送给 `fastembed` 的 `BAAI/bge-small-en-v1.5`，写入 `artifacts/corpus.lance`。第一次要下几百 MB 模型。

如果默认测试套件去下载模型：

- CI 和沙箱经常没有 Hugging Face 网络；
- 失败原因从「chunker 切错了」变成「代理 403」；
- 整场从 0.2 秒变成几分钟。

所以 `test_chunk_and_embed.py` 文件头就写明：embedding **不是**默认单元套件的一部分。测 chunker 时把 `token_counter` 换成「按空格数词」的假计数器，才能在十几个词的假段落上触发「代码块装不下就整块放到下一块」——真实的 480 token 上限太大，假段落永远装得下，那条规则就测不到。

真正要写 LanceDB 时，单独跑脚本，并且可以先跳过 embed：

```bash
cd rag
TIER_B_SKIP_EMBED=1 .venv/bin/python build/chunk_and_embed.py
# 有网、要出 corpus.lance 时再去掉这个环境变量
```

---

## 9. 这一轮实际敲过的命令和结果

日期：2026-08-28。全部在 `rag/` 下、用 `.venv/bin/python`（CPython 3.11.15）。

### 9.1 单元测试（主验收）

```text
platform darwin -- Python 3.11.15, pytest-9.1.1
rootdir: .../godot3_to_4_migration_agent/rag
configfile: pyproject.toml
collected 33 items
...
============================== 33 passed in 0.19s ==============================
```

33 条全部 PASS。这是这一轮对「代码有没有按 CHUNKING.md 工作」的验收标准。

中间曾经把 `test_process_github_keeps_maintainer_and_code` 和 `test_process_github_keeps_opening_post` 粘成一条（两段 Arrange 写进同一个函数）。后来拆开了：一条锁「broken HTML 快照里的 opening post 要留、Uh oh / Please reload 要丢」，一条锁「maintainer 散文 + 任意作者的代码块要留、`+1` 要丢」。**一条用例只证明一件事**，失败时才知道改哪段 if。

### 9.2 对着真实 vault 跑一遍流水线（不是 pytest）

单元测试用的是假输入。假输入全绿，不代表 parser 对 21 个真文件不会吐出空 IR。所以在 pytest 之外又跑了编译脚本。顺序和 `CHUNKING.md` 的三阶段一致：

```bash
.venv/bin/python build/scan_tier_b_raw.py
.venv/bin/python build/process_official_gdscript_doc.py
.venv/bin/python build/process_official_html_doc.py
.venv/bin/python build/process_official_blog.py
TIER_B_SKIP_GITHUB_API=1 .venv/bin/python build/process_github.py
.venv/bin/python build/process_community.py
.venv/bin/python build/compile_curation.py
TIER_B_SKIP_EMBED=1 .venv/bin/python build/chunk_and_embed.py
```

`TIER_B_SKIP_GITHUB_API=1` 是因为 `_raw/github_*` 里已经有 HTML 快照；issue 6265 那份快照本身是 GitHub 的「Uh oh! Please reload」错误页，打 API 才拿得到正文。测试和本地无网时都走快照路径。处理器后来加了「opening post 保留 + chrome 丢弃」，6265 从 0 个 block 变成 4 个。

各步打印（摘录）：

| 步骤 | 结果 |
|------|------|
| scan | 21/21 文件写出 `after_preprocess/**/*.blocks.jsonl` |
| official_gdscript_doc | 3 个 IR（basics 69 / styleguide 15 / signals 70 blocks） |
| official_html_doc | 3 个 IR（134 / 132 / 66） |
| official_blog | 2 个 IR（22 / 42） |
| github（跳过 API） | 5 个 IR（含 6265 的 4 blocks、discussion 6192 的 8 blocks） |
| community | **不写 IR**；`prose_review_queue.jsonl` 114 条候选 |
| compile_curation | no-op（`curation/` 还是空的，这是设计：F/G 必须人工 YAML） |
| chunk `--skip-embed` | type A 提升出一批 degenerate docs + 13 份 IR → **74 docs / 178 chunks**，然后跳过 embed |

`gdscript_basics` 的 IR 里仍然看得到 `ONREADY_WITH_EXPORT` 那一段。RST 解析现在跳过 simple table（keyword / operator 表曾经整表漏进 type B，还夹着 docutils 的 `:ref:` 噪音）。

### 9.3 试过一次真 embed，没写进 LanceDB

去掉 `TIER_B_SKIP_EMBED` 之后，chunk 阶段同样得到 178 chunks，随后 `fastembed` 去 Hugging Face 拉 `BAAI/bge-small-en-v1.5`，在当前环境里收到 `httpx.ProxyError: 403 Forbidden`。chunker 没问题，是模型下载被拦了。

所以这一轮**验收停在「chunk 列表稳定 + pytest 33 绿」**。`artifacts/corpus.lance` 要等你在能访问 Hugging Face 的机器上跑：

```bash
cd rag
.venv/bin/python build/chunk_and_embed.py
```

第一次会下载模型（之后走本地 cache）。成功的话会覆盖写出 `rag/artifacts/corpus.lance`。

---

## 10. 你自己要加一条测试时，照着抄

假设你改了 `filters.py` 里的 boilerplate，想锁住「Donate 页脚必须丢掉」：

1. 打开 `test/test_prose_preprocessing_util.py`（测的是 util，不是某个 process 脚本）。
2. 在文件末尾加：

```python
def test_boilerplate_drops_donate() -> None:
    block = _block("Donate to Godot and keep the engine free.")
    kept = boilerplate_filter([block], patterns=["donate"])
    assert kept == []
```

3. 只跑这一条：

```bash
cd rag
.venv/bin/pytest test/test_prose_preprocessing_util.py::test_boilerplate_drops_donate -v
```

4. 先看它**红**（如果过滤器还没写），再看它**绿**（写完之后）。这就是 TDD 的最小循环。不是必须先红后绿，但「一条断言 ↔ 一条规则」这个习惯要留下。

如果测的是「某个 process 脚本会不会把真实 vault 写坏」：用 `tmp_path` 写假 jsonl，调用 `process_file`（它只返回 `ProseDocument`，不写盘），不要调用 `main()`。`main()` 是给人类在终端跑的入口。

---

## 11. 和 A 层测试的边界（故意不碰）

`test/test_build_artifacts.py` 在这一轮之前就存在。它打开 `artifacts/rules.db`，检查 schema_version、重命名条数之类的 A 层不变量。

这一轮的约束是 **不修改 A 层已有代码**。所以：

- 没有改 `parse_renames_cpp.py` / `diff_extension_api.py` / `parse_upgrading_docs.py` / `build_tier_a.py` / `_util.py`；
- 没有改 `test_build_artifacts.py`；
- `rag/retriever/schemas.py` 只在文件末尾**追加**了 `ProseChunk`，没有动 `MigrationRule`。

以后你跑「整个 test 目录」：

```bash
cd rag
.venv/bin/pytest -v
```

如果 `rules.db` 不在，A 层那几条会 `pytest.skip`（它自己检查了文件在不在），B 层 33 条不受影响。这是 fixture 里 `pytest.skip(...)` 的典型用法：缺产物就跳过，不要把「还没编译 A 层」伪装成「B 层 chunker 坏了」。

---

## 12. 这一轮可以记住的五句话

1. **测试是给未来的你看的说明书。** 函数名写成人话，夹具写成最小例子，失败时 10 秒内能定位到一层。
2. **pytest 只负责发现 `test_*` 和提供夹具。** 业务判断全部是你的 `assert`。
3. **`conftest.py` 对齐 import 世界。** build 脚本怎么找 `prose_preprocessing_util`，测试就怎么找。
4. **`tmp_path` + `monkeypatch` 保护真实 vault。** 测试可以读假数据、可以读一份锚定用的真 RST，但不准写回 `ir/` 和 `review_queue.jsonl`。
5. **慢的、要联网的，不要放进默认套件。** chunker 进 pytest；embedding 进「有网时手动跑的脚本」。
