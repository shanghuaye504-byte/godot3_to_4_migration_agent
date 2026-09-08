# 上一轮实际做了什么：解析规划、uv 包管理、以及为什么要这么写

> 这篇文档不是协议说明书。协议在 [`rag/build/README.md`](../rag/build/README.md)，解析方法在 [`rag/build/PARSING.md`](../rag/build/PARSING.md)，包怎么用在 [`rag/README.md`](../rag/README.md)。
>
> 这篇是给「当时没盯着屏幕、但想把这件事学会」的人看的：上一轮任务要解决什么、过程里踩了哪些坑、`pyproject.toml` / `uv` / 依赖组到底是什么意思。把它当课堂笔记，不当权威设计。

---

## 0. 先把任务本身说清楚

用户当时的要求可以拆成四件事，而且明确说了**不要改已经定好的规划**（也就是 `rag/build/README.md` 里的 schema、数据流、两阶段编译）：

1. 规划四类源文件**具体怎么解析**：有现成库就用库，正则能解决就用正则，需要新库就选好。
2. 把 `rag/` 做成一个可以 `import rag.xxx` 的 Python 包，把 **uv 版本管理、依赖分组、项目级打包** 一并落地。
3. 版本管理相关的文件放 `rag/`，编译器方案（怎么解析）放 `rag/build/`，写一份 markdown。
4. 生成一份 Cursor 规则，把后续 agent 最容易搞反的决策记下来。

范围边界也很重要：**没有去实现** `parse_renames_cpp.py` 那些 adapter 的具体逻辑。那些文件当时还是空 stub。上一轮做的是「方法规划 + 打包脚手架」，不是「把编译器写出来」。

最终产出：

| 文件 | 角色 |
|------|------|
| `rag/build/PARSING.md` | 四类源怎么解析（库 / 正则 / 边界） |
| `rag/pyproject.toml` | 包元数据 + 依赖分组 + 打包映射 |
| `rag/setup.cfg` | 把 setuptools 临时目录从 `build/` 挪走 |
| `rag/uv.lock` | 锁死精确版本，保证别人 `uv sync` 出来一样 |
| `rag/.python-version` | 告诉 uv 用 Python 3.11 |
| `rag/__init__.py` | 让 `rag` 成为一个真正的包 |
| `rag/README.md` 末尾一节 | 开发环境怎么用 uv |
| `.gitignore` | 忽略 `.venv/`、`dist/`、`.setuptools-build/` 等本机产物 |
| `.cursor/rules/rag-knowledge-base.mdc` | 给后续 agent 的硬约束 |

下面按「为什么 → 怎么做 → 结果」讲。包管理那一块会讲得特别慢，因为那才是这一轮真正需要学会的东西。

---

## 1. 解析方法规划：不是「能解析就行」，是「每种源配一种最薄的工具」

这一步的目的，是把「以后写 adapter 时该用什么」写死，避免下一轮动手时再争论「要不要上 libclang」「要不要手写 RST 表格正则」。

先看了真实的源文件，再选型。不是凭印象猜。

### 1.1 `renames_map_3_to_4.cpp`：纯正则

打开文件会看到整篇都是同一种形状：

```cpp
const char *RenamesMap3To4::gdscript_function_renames[][2] = {
    { "instance", "instantiate" },
    // { "FLAG_MAX", "PARTICLE_FLAG_MAX" }, // 注释掉的条目
};
```

这不是任意 C++ 代码，是固定格式的二维字符串数组。上 `pycparser` 或 `libclang` 等于用语法分析器去读一张表，过度设计。所以决定：

- 用一条正则抓「数组开始」（数组名 → `symbol_kind`）
- 用另一条正则抓「条目行」（含不含 `//` 注释前缀，决定 `source` 是 `official_renames` 还是 `official_renames_skipped`）
- 遇到 `};` 结束当前数组
- 解析完必须打印报告：识别了多少条、跳过多少条、多少行完全没匹配。未识别行数大于 0 就非零退出——不允许静默漏数据

C# 那几个数组故意整组跳过，这是 `build/README.md` 已经定过的业务规则，不是解析失败。

### 1.2 `extension_api_*.json`：标准库 `json`

两份文件都是普通 JSON。`json.load()` 之后按类名、方法名做集合差：只在 4.0 有 → 删除；只在目标版本有 → 新增；两边都有但签名不同 → 改签名。

`hash` 字段故意不参与比较（hash 变了但参数没变，视为没变）。`builtin_class_sizes` 这类 ABI 细节直接跳过，修 GDScript 用不上。

不引入额外库。

### 1.3 七份 `upgrading_to_godot_4.{1-7}.rst`：用 docutils，不用手写切列

这是选型里最需要解释的一个。

Godot 文档用的是 RST **simple table**：列宽靠一行 `====` 的分段决定，中间还夹着 `✔️` / `❌` 这种多字节符号。更麻烦的是语义跨行：

```text
**Basis**                          ← 这一行只有第一列，是 owner
Method ``looking_at`` adds ...     ← 下一行才是真正的变更
```

如果手写正则按空格数切列，七份文件列宽还不一样，某一张表悄悄切错了你可能根本看不出来。docutils 是 Sphinx 渲染这些文件用的库，让它切表，比自己猜边界可靠。

实际写解析时还要处理两件预处理：

1. `|✔️|` 是 RST 替换引用，定义文件不在我们这份单文件快照里。直接喂给 docutils 会报 Undefined substitution。解决办法不是改表格里的字符（改了会破坏列对齐），而是在文件最前面自动补上「把 `|✔️|` 替换成它自己」的定义。
2. `:ref:` 是 Sphinx 专有角色，docutils 不认识。把报错级别调高，让它警告但不中断——我们不需要跳转目标，只要文本。

变更分类靠一份「覆盖大多数、不假装覆盖全部」的正则表（`removed` / `renamed to` / `adds a new parameter` 等）。这些句式不是猜的，是对七份文件实际抽样统计出来的。匹配不上的自由句式**不丢弃**，仍然产出一行并打 `needs_review`，让人去扫报告。

抽不出符号对的散文，写入 `vault/tier_b_prose/*.prose.jsonl`，作为**下一阶段**向量库的原材料。本阶段不生成 embedding。

### 1.4 `upgrading_to_godot_4.rst` 的 Updating shaders：人工 YAML，不是自动抽

3→4 总指南整篇进 `agent_context/`。唯一例外是 Updating shaders 小节。但那四行结构化规则（例如 `vertex()` 拆成 `start()` + `process()`）是人读过之后判断出来的语义，文件里甚至不是表格行。没有正则能安全归纳「这是一次函数拆分」。所以规划里写死：这四行做成 `tier_a_manual/` 下的小 YAML fixture，`source=official_prose_3to4_shader`，由 `build_tier_a.py` 当普通 YAML 读入。parser 只负责把这一小节的剩余散文搬到 `tier_b_prose/`。

### 1.5 YAML：`yaml.safe_load`

`semantic_rewrites.yaml` 已经接近最终表结构。格式错了就让 `yaml.safe_load` 直接报错退出，不做兼容兜底——这是人维护的文件，宽松解析只会把错藏起来。

### 1.6 解析规划的结果

写成了 [`rag/build/PARSING.md`](../rag/build/PARSING.md)。它只讲「怎么解析」，字段名叫什么仍然以 `build/README.md` 为准，两份文档不互相抄。`build/README.md` 开头加了一句交叉引用。

parser 脚本本身没写。这是故意的。

---

## 2. 包管理入门：先建立几张图

如果你没用过 Python 的「项目级依赖管理」，下面这些词会混在一起。先分开。

### 2.1 系统 Python、虚拟环境、项目，是三层东西

电脑上装的 `python3` 是**系统解释器**。你在终端敲 `pip install pydantic`，默认会装进这个系统环境。过几个月另一个项目要另一个版本的 pydantic，两个项目就开始互相踩。

**虚拟环境（venv）** 是项目自己的一份 Python：一份独立的 `python` 可执行文件 + 一份独立的 `site-packages`（第三方库放这里）。进入这个环境之后，`import pydantic` 用的是这份里的库，跟系统、跟别的项目无关。

**项目** 是「我这个目录要被当成一个可安装的包」。光有 venv 还不够——还需要一份清单告诉工具：包叫什么、依赖哪些库、哪些文件算「包的一部分」。这份清单在现代 Python 里就是 `pyproject.toml`。

关系可以记成：

```text
系统 Python 3.14          ← 本机碰巧装了这个，不要直接往里面 pip install 项目依赖
        │
        ▼
uv 根据 .python-version    ← 我们写的是 3.11，所以 uv 会去下载/使用 3.11
创建一个 rag/.venv/
        │
        ▼
.venv 里面装着：
  - Python 3.11
  - pydantic、lancedb（运行时）
  - 可选的 docutils、pytest……（按你这次 sync 的组）
  - 一份「可编辑安装」的 rag 包本身
```

### 2.2 为什么不用「在仓库根目录一个大 venv」

`rag/` 里其实有两种完全不同的代码：

- `retriever/`：Agent 运行时每个 worker 都要 import。依赖要**轻**：pydantic + lancedb 就够。
- `build/`：只在本机编译知识库时跑一次。依赖可以**重**：docutils、PyYAML，以后还可能有 GitPython。

如果全塞进同一个「运行时依赖列表」，Docker 镜像就会被迫带上解析 RST 的库、git 客户端这些生产根本用不到的东西。镜像变大、启动变慢、出问题的面变宽。所以设计从一开始就是：

- 运行时依赖写在 `[project.dependencies]`
- 编译依赖写在 `[dependency-groups] build`
- 测试/lint 写在 `[dependency-groups] dev`

worker 镜像只装第一组。

### 2.3 pip、venv、uv 各自干什么

| 工具 | 它解决什么 | 它不解决什么 |
|------|-----------|-------------|
| `pip` | 从一个地方把包装进当前 Python | 不管「这个项目该用哪一版 Python」；默认也不锁死全树精确版本 |
| `python -m venv` | 建一个空的虚拟环境 | 不管依赖解析、不管 lockfile |
| `uv` | 上面两件事一起做，而且还更快 | 它不是语言本身的一部分，是一个独立的包管理器 |

可以把 uv 理解成：**venv + pip + 一个会算依赖图并写出 lockfile 的解析器**，速度很快。本机当时已经装了 `uv 0.11.2`。

核心命令只有三个，上一轮都实测过：

```bash
cd rag

# 按 pyproject.toml + uv.lock 把环境搭好（可编辑安装 rag 自己）
uv sync --group build --group dev

# 只装运行时依赖，模拟 worker 镜像
uv sync --no-default-groups

# 打出一份可以拷进 Docker 的 wheel（不是可编辑安装）
uv build --wheel -o dist/
```

「可编辑安装」的意思：代码还在你的工作目录里，改 `.py` 立刻生效，不用每次重装。生产环境不要用这个——生产要的是一份冻住的 wheel。

### 2.4 lockfile 是什么，为什么要提交

`pyproject.toml` 里写的是**范围**：`pydantic>=2.7` 表示「2.7 以上都行」。今天解析可能装上 2.13.4，三个月后可能变成 2.20。评测实验、同事的机器、CI，就会各装各的。

`uv.lock` 是解析器把范围**算成精确版本**之后写下的快照（上一轮生成的那份大约 176KB、870 行）。任何人 `uv sync` 都会按这份锁来装，而不是重新「今天 PyPI 上最新的是啥」。

所以：

- `uv.lock` **要提交进 git**
- `.venv/` **不要提交**（那是本机装出来的目录，体积大、平台相关）
- `dist/`、`*.egg-info/`、`__pycache__/`、`.setuptools-build/` 也不要提交

这些忽略规则已经写进仓库根目录的 `.gitignore`。

---

## 3. `pyproject.toml` 逐段拆开讲

文件在 [`rag/pyproject.toml`](../rag/pyproject.toml)。下面按段落解释「这一段在干什么」，而不是复述文件本身。

### 3.1 `[project]`：这个包对外是谁

```toml
[project]
name = "rag"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "pydantic>=2.7",
  "lancedb>=0.37",
]
```

- `name`：别人 `pip install` / `import` 时用的名字。这里叫 `rag`，所以装完是 `import rag`。
- `requires-python`：低于 3.11 的解释器直接拒绝。和 `.python-version` 里写的 `3.11` 是配套的：前者是「最低能跑」，后者是「本项目默认用哪一版」。
- `dependencies`：运行时依赖。**只有 worker 真正 import 得到的东西才该出现在这里。** docutils 解析 RST 用得到，但 retriever 运行时用不到，所以不写在这里。

`>=2.7` 这种写法叫版本范围。真正装哪一版由 lockfile 钉死。

### 3.2 `[dependency-groups]`：同一份项目，三种装法

这是 PEP 735 引入的「依赖组」。它不是「可选功能」（那叫 extras，给用户按需装的），而是「同一份代码在不同场合需要的工具箱」：

```toml
[dependency-groups]
build = ["docutils>=0.21", "pyyaml>=6.0", "requests>=2.32", "gitpython>=3.1"]
dev   = ["pytest>=8.0", "ruff>=0.6"]
```

`requests` 和 `gitpython` 当时还没有脚本真正用到，是给未来「按官方 tag 刷新 vault」占位的。占位写在 `build` 组里，不会污染运行时镜像。

这里有一个 uv 的历史坑，上一轮实测踩到了：

- 组名恰好叫 `dev` 时，`uv sync` **不加任何参数也会把 `dev` 装上**。这是 uv 的默认行为。
- 自定义组名（我们的 `build`）不会被隐式装上，必须 `--group build`。
- 想要「只装 `[project.dependencies]`」必须 `uv sync --no-default-groups`。只写 `--no-group dev` 不够干净，因为默认组策略以后可能变。

实测结果（用独立 venv 验证，避免污染本机 `.venv`）：

| 命令 | 装上了什么 |
|------|-----------|
| `uv sync --group build --group dev` | pydantic、lancedb、docutils、pyyaml、requests、gitpython、pytest、ruff |
| `uv sync`（无参数） | 运行时 + **dev**（pytest/ruff 会来），**没有** build 组 |
| `uv sync --no-default-groups` | 只有 pydantic + lancedb |

所以文档和规则里都写了：验证「模拟 worker 镜像」必须带 `--no-default-groups`。

### 3.3 `[build-system]`：谁负责把目录变成可安装的包

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

Python 打包分两步：

1. **后端（build backend）** 读你的源码目录，按规则决定哪些文件进入一份 wheel。
2. **前端（uv / pip）** 调用这个后端。

常见后端有 hatchling、setuptools。上一轮先试了 hatchling：它默认假设「目录名就是包名」，而我们的布局是「`rag/` 目录里直接放 `retriever/`，没有再套一层 `rag/rag/`」。hatchling 要把「当前目录的文件」映射成「wheel 里的 `rag/` 前缀」，试了几种 `sources` 写法都不干净。setuptools 有一个老但明确的开关：`package-dir = {"rag" = "."}`，一次就对了。所以选了 setuptools，不是因为「setuptools 更新」，而是因为它正好能表达我们这种「目录和包名错一层」的布局。

### 3.4 最反直觉的一段：`package-dir` 和 `packages`

物理目录是这样的（简化）：

```text
rag/                          ← 这是 uv 项目根，也是 pyproject.toml 所在处
├── pyproject.toml
├── __init__.py               ← 希望变成 rag/__init__.py
├── retriever/                ← 希望变成 rag/retriever/
│   └── ...
├── build/                    ← 不要打进 wheel
├── vault/                    ← 不要打进 wheel
└── artifacts/                ← 不要打进 wheel（数据另拷，不走 pip）
```

标准教科书布局其实是：

```text
rag/
├── pyproject.toml
└── rag/                      ← 多套一层，包名和文件夹同名
    ├── __init__.py
    └── retriever/
```

我们**没有**那一层 `rag/rag/`。原因是既定目录树已经把 `vault/`、`build/`、`retriever/` 平铺在 `rag/` 下，再套一层会把整份规划打乱。

setuptools 的翻译是：

```toml
[tool.setuptools]
package-dir = { "rag" = "." }
packages = ["rag", "rag.retriever"]
```

人话：

- `package-dir`：「名叫 `rag` 的包，源码就在当前目录 `.`，不要再往下找一个叫 `rag` 的子文件夹。」
- `packages`：「请把 `rag` 和它的子包 `rag.retriever` 收进去。」**没列出来的目录就不会进 wheel。** 所以 `build/`、`vault/` 进不去——这正是我们要的。

`uv build --wheel` 之后用 `unzip -l dist/rag-*.whl` 看到的内容只有：

```text
rag/__init__.py
rag/retriever/__init__.py
rag/retriever/cache.py
rag/retriever/router.py
rag/retriever/schemas.py
rag/retriever/tier_a.py
rag/retriever/tier_b.py
rag-0.1.0.dist-info/...
```

没有 vault，没有 build，没有 artifacts。这条边界被实测确认过。

有一个副作用必须知道：本地 `uv sync` 是**可编辑安装**。Python 会把当前目录直接挂到 import 路径上。这时 `import rag.build` 可能也不会报错——因为 `build/` 就在旁边，隐式命名空间包会把它当成 `rag.build`。这**不是**配置写错了，是可编辑安装的已知特性。生产走的是上面那个 wheel，wheel 里没有 `build/`，镜像里就 import 不到。规则文件里专门写了这一条，免得以后有人「修」掉 `package-dir`。

`__init__.py` 故意几乎是空的：不要在包入口 import retriever。否则以后谁 `import rag` 都会把 lancedb 一起拉起来，build 脚本并不需要那样。

### 3.5 撞名事故：为什么还要一个 `setup.cfg`

setuptools 打包时会在项目根下建一个临时目录，默认就叫 `build/`。我们自己的 adapter 脚本也放在 `rag/build/`。第一次 `uv build` 之后，`rag/build/` 里突然多出 `lib/`、`bdist.macosx-.../`，和真正的 `parse_renames_cpp.py` 混在一起。

这不是业务 bug，是两个东西抢同一个文件夹名。

解决办法是告诉 setuptools：「你的临时目录请改名叫 `.setuptools-build/`」。setuptools 认 `setup.cfg` 里的：

```ini
[build]
build-base = .setuptools-build
```

改完再 `uv build`，`rag/build/` 只剩下我们自己的文档和脚本。`.setuptools-build/` 已加入 `.gitignore`。

为什么不写进 `pyproject.toml`？因为 setuptools 的这个 `build-base`  historically 读的是 `setup.cfg` 的 `[build]` 段。能用最少的文件把坑堵上，就不必再绕一层。

---

## 4. 上一轮实际操作过程（按时间顺序）

下面是「当时到底敲了什么、看到了什么」，方便把前面的概念对上号。

1. **摸清现状。** 仓库里 `rag/pyproject.toml` 当时是空文件；`rag/retriever/__init__.py` 也是空的。本机有 uv 0.11.2，系统 Python 是 3.14，所以更需要 `.python-version` 把开发版钉在 3.11，而不是「碰巧用了机器上最新的」。
2. **抽样源文件。** 看了 cpp 的数组形状、`extension_api` 的顶层键（`classes` / `builtin_classes` / …）、七份 rst 的表格和动词句式统计（`adds a new … parameter` 是最大类），以及 `Updating shaders` 在 3→4 总指南里的位置。这些观察直接写进了 `PARSING.md`，避免下一轮写 parser 时再凭记忆选型。
3. **在 `/tmp` 里做布局实验，不直接改仓库。** 先试 hatchling 的 `sources` 映射：wheel 里文件落在根上，`import rag` 失败。再试 setuptools 的 `package-dir = {"rag" = "."}`：wheel 里是 `rag/__init__.py` + `rag/retriever/...`，`import rag.retriever` 成功。这才把方案写进真正的 `pyproject.toml`。
4. **写正式文件并 `uv sync`。** uv 按 `.python-version` 下载了 CPython 3.11.15，创建 `rag/.venv`，解析 34 个包（含 lancedb 的一串原生依赖如 pyarrow、numpy）。`from rag.retriever import ...` 以及 `import docutils, yaml, pydantic, lancedb` 全部通过。
5. **打 wheel 验边界。** 确认 vault/build 不在 wheel 里。
6. **发现 `dev` 组被默认装上。** 无参数 `uv sync` 之后 pytest/ruff 在，docutils 不在。于是文档改成：模拟生产必须 `--no-default-groups`。用 `UV_PROJECT_ENVIRONMENT` 指到 `/tmp` 的独立 venv 验证过：那边确实只有 pydantic + lancedb。
7. **发现 `build/` 被 setuptools 污染。** 加 `setup.cfg` 重定向，再打一次 wheel，确认 `rag/build/` 干净。
8. **补 README 开发环境一节、`.gitignore`、Cursor 规则。** 规则的 `globs: rag/**`，只在碰 rag 目录时生效，避免把这些约束塞进全仓库的 `.cursorrules`。

中途删 `.venv` 被沙箱拦住过一次（`.venv` 里有只读的原生库文件）。后来在用户批准后清掉重建。这不影响设计，只说明「虚拟环境一旦装了带原生扩展的包，删的时候权限会比较烦」。日常开发不需要反复删 `.venv`，改依赖后重新 `uv sync` 即可。

---

## 5. 日常你真正需要记住的命令

在 `rag/` 目录下：

```bash
# 第一次，或者依赖变了之后：把本机开发环境配齐
uv sync --group build --group dev

# 之后写 retriever / 跑测试，用这个解释器，不要用系统 python3
.venv/bin/python -c "import rag, rag.retriever; print('ok')"
.venv/bin/pytest
.venv/bin/ruff check .

# 怀疑「生产镜像会不会太胖」时，用这条核对运行时依赖
uv sync --no-default-groups   # 建议在临时目录做，别覆盖你的开发 .venv

# 给 Docker / 发布用
uv build --wheel -o dist/
unzip -l dist/rag-*.whl       # 确认没有 vault/、build/
```

改了 `pyproject.toml` 的依赖范围之后，要再跑一次 `uv sync`，让 `uv.lock` 更新，并把 lockfile 一起提交。只改 toml 不更新 lock，别人的环境和你的会对不上。

不要 `pip install` 到系统 Python。不要 `git add rag/.venv`。不要为了「看起来整齐」去新建 `rag/rag/` 嵌套目录——`package-dir` 就是为了避免那样改规划。

---

## 6. Cursor 规则为什么要单独写一份

[`.cursor/rules/rag-knowledge-base.mdc`](../.cursor/rules/rag-knowledge-base.mdc) 不是给人类看的教程，是给后续 agent 的「禁止回头」清单。人会读这篇 walkthrough；agent 打开 `rag/**` 时会读那份规则。里面记的都是已经拍板、但下一轮很容易凭直觉改回去的事，例如：

- 字段设计以 `build/README.md` 为准，总览文档迁就它，不要反过来改 schema
- 分流靠 `detection_method`，不要发明 `guard_false_positive` 这种布尔列
- 版本比较走整数编码，不要比 `"4.10" < "4.9"`
- YAML 只 insert，不做 overlay
- A/B 两层同时查，不要 A 命中就短路
- Updating shaders 的四行是人工 YAML，不要写 NLP 去抽
- 散文进 `vault/tier_b_prose/`，本阶段不碰 LanceDB
- 包布局不要重新套一层目录
- setuptools 的临时 `build/` 已经重定向，看到 `lib/`、`bdist.*` 先查 `setup.cfg`

---

## 7. 这一轮明确没有做的事

- 没有实现任何一个 adapter 的解析逻辑（`parse_renames_cpp.py` 等仍是 stub）
- 没有生成 embedding，没有写 `corpus.lance`
- 没有改 `build/README.md` 的字段协议（只加了指向 `PARSING.md` 的一句）
- 没有 `git commit` / `git push`

如果你下一步要「按 `PARSING.md` 把四个 adapter 写出来」，那是新任务，和这一轮的打包脚手架是分开的。

---

## 8. 读完这篇之后，权威文档怎么接力

| 你想搞清楚的问题 | 去哪看 |
|------------------|--------|
| 一行规则有哪些字段、谁来填 | [`rag/build/README.md`](../rag/build/README.md) |
| 四种源具体用什么库、正则怎么写 | [`rag/build/PARSING.md`](../rag/build/PARSING.md) |
| 检索怎么融合、Agent 工具长什么样 | [`rag/retriever/README.md`](../rag/retriever/README.md)、[`rag/retriever/docs/`](../rag/retriever/docs/README.md) |
| 目录职责、开发时怎么 uv sync | [`rag/README.md`](../rag/README.md) |
| 依赖和打包的精确配置 | [`rag/pyproject.toml`](../rag/pyproject.toml)、[`rag/setup.cfg`](../rag/setup.cfg) |
| 后续改 rag 时不要踩的坑 | [`.cursor/rules/rag-knowledge-base.mdc`](../.cursor/rules/rag-knowledge-base.mdc) |

这篇 walkthrough 只负责把「上一轮为什么这么干」讲明白。配置改了以后，以仓库里的实际文件为准，不要拿这篇当过时配置的复印件。

---

## 9. 学习心得（后来问清楚的几件事）

能 `import rag`，不是因为当前目录在 `rag/` 里，而是因为**正在跑的那个 Python 已经安装过这个包**。`uv sync` 填满的是 `rag/.venv`；换系统 `python3`，人还站在 `rag/` 里也会失败。`import` 不会再带进一套 Python，只是在当前进程里加载模块。

**说明书 vs 存货：** `pyproject.toml` 是需要什么（uv、pip、打包都读它）；`uv.lock` 是精确版本；`.venv` 是装出来的结果，不是给 uv 看的另一份配置。两边都写 pydantic，是「声明需要」和「这间厨房已经买好了」，不是分工给 uv 和打包各看一份。

1. **`uv.lock` 第一次没有，要算出来。** 首次 `uv sync` / `uv lock` 按 toml 的范围解析依赖图并写盘；提交 lock 之后别人 sync 按它装，不再每天换最新版。改了 toml 再 sync，lock 才会更新。

2. **`uv build --wheel` 不打 `build`/`dev` 组，也不打 pydantic 的代码。** 盒子里主要是 rag 自己的 `.py`，封面上写着还需要 `pydantic>=2.7`、`lancedb>=0.37`。`pip install` 这个 wheel 时，pip 会把 rag 装进**当前环境**，再按封面去 PyPI 把 pydantic 等装进**同一份环境**。`rag/.venv` 不会跟着走。

3. **Agent 里可以用 `pip install -e`（路径可编辑），wheel 是发版/Docker 的常规做法。** 想让用户「进 Agent 环境就能用 rag、不用自己找 wheel」：在 **Agent 的** `pyproject.toml` 里声明 rag 依赖，用户只 `uv sync`。开发期用路径/`-e`；镜像里再 `pip install` wheel。责任在 Agent 项目，不在用户。

4. **`pip install 包名` 能用，是因为有人把 wheel 传到了 PyPI。** 本地这份 `rag` 没上架，只能路径安装、装 `.whl`，或让 Agent 的 toml 写成 path 依赖。机制和第 2 条一样，只是货架从「手里的文件」换成了「公共索引」。

5. **生产 Docker 装的是整份 worker/Agent，不是单独的 RAG 服务。** 容器里 Agent 进程直接 `import rag.retriever`，读本地 `artifacts/`。不要再套 RAG 容器、HTTP 网关、MCP。MCP/REST 只是以后跨语言时的可选外壳。镜像里带「已安装的 rag 库 + artifacts」，不带 `vault/`、`build/` 那些编译期重依赖。Day 1 的 Docker 是带着指定版 Godot 的运行环境，和「RAG 微服务」也不是一回事。

**冲突只发生在同一份 venv 里每个库只能有一个版本。** Agent `import rag` 用的是 Agent 环境里的 pydantic，不会去打开 `rag/.venv`。范围能重叠就共用；Agent 锁 1.x、rag 要 2.x，安装或运行就会炸。`docutils` 等 build 依赖默认不会进 Agent。
