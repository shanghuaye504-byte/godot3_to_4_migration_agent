# inline_tools 架构

本文件锁定本目录的形态和两个只读工具的共同边界。函数尚未实现。签名与验收的细则在 `read/ARCHITECTURE.md` 和 `grep/ARCHITECTURE.md`。

依据是历史讨论和 `PENDINGS.md` 第 1.3–1.4 节、文末「最终实现决定」。不采用 `DESIGN_NOTES.md` 里的子模块目录。

## 1. 这是什么

```text
inline_tools/
├── __init__.py          # 空。只表示这是包
├── README.md
├── ARCHITECTURE.md      # 本文件
├── read/                # 一个工具一个包
├── grep/
└── tests/               # 空测试文件，断言还没写
```

- 一个工具一个文件夹、一个包。以后若加工具，同样只加一个子包，不把多个工具塞进一个 `tools/` 模块。
- 不建 `pyproject.toml`。不在这里做 `uv sync`。
- 不是 MCP server。模型调用的是宿主注册的 Python 函数，参数个数固定。
- 模型没有 Bash，也看不到 argv。给 Bash 之后，模型可以用 `sed -i` 绕过以后的写通道守卫，也可以自己拼 Godot 参数（包括已排除的 `--debug`）。能力边界由最宽的入口决定，所以这里不提供 shell。

本步只存在 `read` 和 `grep`。不建 `edit`、`scene`、`codemod`、`intake` 等目录。

## 2. 工作区与路径

工作区根来自 `codebase_index/config.yaml` 的 `project_root`，或环境变量 `CODEBASE_PROJECT_ROOT`（后者优先，与现有 codeindex / verify 一致）。

模型参数里没有工作区，没有 Godot 二进制，没有 argv。Python 函数可以把 `project_root` 作为宿主注入的第一个参数，测试因此不必改全局配置。

路径规则（两个工具相同）：

- 接受 `res://...`，或相对 `project_root` 的路径。
- 去掉 `res://` 后拼到 `project_root` 下，再 `realpath`。结果必须仍在工作区内。`../` 逃逸拒绝。
- 禁止进入 `.godot/`、`.import/`、`.codeindex/`。这三处是导入缓存、引擎产物和索引状态，不是源码。
- 返回给模型的路径用 `res://` 形式。

## 3. 两个工具为什么分开

| | grep | read |
| --- | --- | --- |
| 输出 | 稀疏、不连续的命中行 | 连续区间，每行带绝对行号 |
| 用途 | 定位：该看哪个文件、哪一行 | 拿到逐字原文，作为以后锚定编辑的锚 |
| 能否代替另一个 | 不能。`-C` 的窗口边界不可控，GDScript 缩进差一个字符锚就对不上 | 不能。它不搜索 |

不单独做 glob 工具。`rg` 自己就能列文件。`grep` 在 `pattern` 为空时退化为列文件，少一个模型要选的工具。

## 4. 这两个工具明确不做

- 不写盘。调用前后工作区字节不变。
- 不调用 `codeindex`，不把结果写进索引。
- 不解析 `.tscn` / `.tres`，不做场景校验，不跑 Godot。场景索引进 codeindex 是 `NEXT_STEP.md` 的后续工作，不放进这两个包。
- 当前 codeindex 仍不索引 `.tscn` / `.tres` / `.gdshader`。在那一步落地之前，`grep` 是模型看见这些后缀的通道。`read` 则按路径读任意允许的文本文件，包括这些后缀。
- 不检索迁移规则（那是 `rag.retriever`）。
- 不提供网络、git、Godot 子进程。

## 5. 与已有代码的关系

verify、codeindex CLI、`rag.retriever` 留在原包，不搬进本目录，也不在这里再包一层 MCP。本步不改那些包。
