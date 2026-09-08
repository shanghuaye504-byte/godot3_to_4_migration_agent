# Godot Agent 代码索引与验证 —— 工业级实现指南 v2

## 0. 最终架构总览

三层，**零 MCP 用在检索上，一个自建 MCP 仅用于校验**:

```
Agent
 ├─ Layer 1  grep/glob            → 直接走 Bash 调 ripgrep，无包装、无工具协议开销
 ├─ Layer 2  符号/调用链结构化查询  → 常驻 daemon（唯一写者）+ 无状态 CLI（Bash 调用，只读）
 └─ Layer 3  校验                  → 自建 godot-mcp（Python），按需拉起 headless 校验子进程
```

三层的取舍逻辑保持不变，但这一版把 Layer 2 的"要不要用 MCP"这个问题彻底解决掉了：**无状态、低延迟的查询，走 Bash + CLI；只有 Layer 3 这种需要真实拉起 Godot 二进制才能拿到的客观信号，才值得包成一个 MCP 工具。** 这也是 Cursor（核心检索能力做成产品原生集成而非 MCP）和 Claude Code（2026 年之后把 Grep/Glob 从独立工具收回、改成直接走 Bash 执行 ripgrep，省掉一次工具协议往返）不约而同在走的方向，不是我们自己拍脑袋的选择。

> **范围降级说明**：原 Layer 3 规划还包含一个常驻 Godot LSP 会话，用于 `hover` 和
> `workspace/symbol` 查询。由于 LSP 会引入不可预测的进程/端口冲突，且时间紧张，
> 现决定**完全去掉 LSP 方案**。引擎内置符号查询与语法错误文件的兜底查询统一由
> Layer 2 的 `codeindex` CLI 承担（必要时可在 Layer 2 内增强 parser 容错，而不引入
> LSP）。

---

## 一、Layer 1：Grep —— 原生，不包装

### 1.1 ripgrep 回顾

ripgrep（`rg`）是 Rust 写的搜索工具：默认遵守 `.gitignore`、多线程扫描、`--json` 输出结构化匹配结果。你的整个 Layer 1 就是这一个二进制。

### 1.2 不要为它单独建工具

**结论：直接让 Agent 通过 Bash 调用 `rg`，不要包 CLI，更不要包 MCP。** 理由很直接：

- 这是纯粹的无状态单次调用，没有连接、没有会话、没有需要维护的进程，包一层只会多一次协议序列化开销，没有任何收益。
- 行业已经验证了这个方向是对的：Claude Code 在做过大量实测后，把原本独立的 Grep/Glob 工具直接收回，改成 Agent 自己拼 `rg`/`find` 命令走 Bash 执行——**因为工具越薄，越应该用最薄的那层去承载它**，专门起一个工具/协议只是为了包一个已经很好用的命令行程序，是不必要的中间层。

唯一需要你手动配置的是排除规则，`.gitignore` 覆盖不到的目录要显式加进去：

```bash
# .rgignore 放在项目根目录，rg 会自动读取，等价于额外的 .gitignore
.godot/
.import/
addons/*/thirdparty/
*.tscn.import
```

Agent 侧只需要知道"这个项目有 `.rgignore`，直接 `rg -e <pattern> --json .` 就行"，不需要更多。

---

## 二、Layer 2：Tree-sitter + SQLite —— daemon + CLI

这一层是你系统里状态最复杂、也最容易踩坑的一层，详细展开。

### 2.1 角色拆分：为什么必须是两个进程，而不是一个

`codeindexd`**（daemon，唯一写者）**：长驻进程，持有文件监听器和 SQLite 的唯一写连接，负责把文件变化增量落库。
`codeindex`**（CLI，无状态读者）**：每次被 Agent 通过 Bash 调用时启动、查询、打印 JSON、退出，只做只读查询，不持有任何长期状态。

拆开的核心原因是**读写生命周期完全不对齐**：查询是"这一秒要，下一秒可能就不需要"的瞬时行为，天然适合无状态 CLI；而增量索引是"必须持续在后台运行，不能因为某次查询结束就退出"的常驻行为。如果把两者塞进一个进程，你要么让每次查询都拖着一个文件监听器一起启动关闭（浪费、且监听器重启会丢失防抖状态），要么让一次性查询也常驻不退出（违反 CLI 应该退出的直觉，调试也麻烦）。拆开之后，**CLI 永远是可以直接在终端敲、立刻看到结果、用完就退出的东西**，这是你要的"容易调试"在这一层的具体体现。

### 2.2 daemon 的生命周期管理

daemon 不应该被动地"第一次查询时自动拉起"——多个 Agent 并发调用 CLI 时，如果每个都去检查"daemon 在不在、不在就拉一个"，会产生竞态（两个 CLI 同时发现 daemon 不在、同时尝试拉起、变成两个写者）。正确做法是**显式的启动命令 + 文件锁**：

```python
# codeindexd 启动时做的第一件事
import fcntl, os, sys

LOCK_PATH = ".codeindex/daemon.lock"

def acquire_singleton_lock():
    os.makedirs(".codeindex", exist_ok=True)
    fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # 独占非阻塞锁
    except BlockingIOError:
        print("daemon already running, exiting", file=sys.stderr)
        sys.exit(1)
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode())
    return fd  # 持有到进程退出，锁自动释放
```

对外暴露的启动方式是一条显式命令：

```bash
codeindex up      # 幂等：daemon 没在跑就拉起并等首次全量扫描完成再返回；已经在跑直接返回
codeindex status  # 查 daemon 是否存活、上次索引时间、待处理队列长度
codeindex down    # 优雅停止
```

`codeindex up` **必须阻塞到首次全量扫描完成才返回**，而不是拉起进程就立刻返回——否则会出现"daemon 刚起来、索引还是空的、Agent 已经在查询"的冷启动竞态，查询结果全是空的会让 Agent 误以为符号真的不存在。判断"首次扫描完成"的方式很简单：daemon 扫完所有文件后往 `.codeindex/ready` 写一个时间戳，`up` 命令轮询这个文件出现再返回。

**在 CI 里的接入方式**：job 开始时第一步跑 `codeindex up`（此时会阻塞几秒到十几秒做全量扫描），扫描完成后再进入正式的 Agent 任务步骤，daemon 常驻到 job 结束，`codeindex down` 作为收尾步骤（或者直接让 job 容器销毁顺带杀掉进程，问题不大，因为 SQLite 文件本身是自洽的，daemon 崩溃不会损坏已经 commit 的数据）。

**本地开发场景**：可以让 `codeindex up` 挂在你启动 Agent 会话的脚本最前面，或者做成 systemd user service / macOS launchd agent 常驻，看你团队的使用习惯，这个不影响架构本身。

### 2.3 更新时序：防抖策略，以及一个 Agent 场景特有的坑

**被动路径（watcher 触发，应对人类编辑、git checkout、其他工具生成代码等外部变化）：**

标准做法是"静默期防抖"（quiescence debounce）：每来一个文件变化事件就重置一个计时器，只有连续 N 毫秒没有新事件才真正触发重建。这对突发性的连续写入（比如编辑器自动保存、Agent 一次改好几个文件）特别合适，因为它把一串密集变化合并成一次重建，而不是每个文件变化都单独触发一次：

```python
import threading, time

class DebouncedIndexer:
    def __init__(self, quiescence_ms=500, max_wait_ms=2000):
        self.quiescence = quiescence_ms / 1000
        self.max_wait = max_wait_ms / 1000
        self.pending = set()          # 本轮待重建的文件集合
        self.timer = None
        self.first_pending_at = None
        self.lock = threading.Lock()

    def on_file_changed(self, path):
        with self.lock:
            self.pending.add(path)
            if self.first_pending_at is None:
                self.first_pending_at = time.monotonic()
            if self.timer:
                self.timer.cancel()

            elapsed = time.monotonic() - self.first_pending_at
            # 硬上限：即使事件一直在来，超过 max_wait 也强制 flush
            # 避免 Agent 连续密集编辑时索引被无限期推迟
            delay = min(self.quiescence, max(0, self.max_wait - elapsed))
            self.timer = threading.Timer(delay, self._flush)
            self.timer.start()

    def _flush(self):
        with self.lock:
            batch = list(self.pending)
            self.pending.clear()
            self.first_pending_at = None
        reindex_batch(batch)   # 见 2.4，单个事务里处理整批文件
```

推荐参数：**静默期 500ms，硬上限 2000ms**。500ms 是"人类保存文件的间隔"和"Agent 一次工具调用内连续写几个文件的间隔"之间取的经验值——太短会导致同一个文件保存两次触发两次重建（浪费），太长会让查询等太久。2000ms 硬上限保证即使变化事件持续不断，索引也不会被无限期推迟。

**主动路径（Agent 自己刚编辑的文件，需要"读到自己刚写的东西"）：**

这是一个纯被动 watcher 方案会漏掉的关键问题：**防抖设计的前提是"变化来源不可预测、需要等它安静下来"，但 Agent 编辑自己的文件不是这种模式——它写完一个文件的下一步动作往往就是紧接着查询这个文件里的符号，如果还要等 500ms 的静默期，对 Agent 的工作流来说是不必要的延迟。** 解决方式是给 Agent 的文件编辑工具直接挂一个同步钩子，绕开防抖：

```bash
# Agent 编辑完文件后，工具链里紧跟着调用（同步阻塞，通常几毫秒到几十毫秒）
codeindex sync path/to/player.gd
```

`sync` 命令的实现是直接对指定文件做一次同步的、不经过防抖计时器的立即重建（内部复用 2.4 的 `reindex_batch`，只是 batch 里只有这一个文件），完成后再返回。**如果你能控制 Agent 的文件写入工具（比如你的 Agent 框架里有统一的 `write_file`/`str_replace` 实现），最好的做法是把 `codeindex sync <path>` 直接挂在这个工具的写入完成之后自动调用，Agent 不需要自己记得调**，这样"读自己刚写的东西永远是最新的"这个保证是系统自动给的，不依赖 Agent 的行为规范。如果控制不了（比如 Agent 框架是第三方黑盒），退而求其次在系统提示里告诉 Agent"编辑完 `.gd`/`.cs` 文件后如果马上要查符号，先调一次 `codeindex sync <文件>`"。

被动 watcher 依然保留，作为"Agent 编辑工具之外发生的变化"（人类协作者同时在改、git pull、其他脚本生成代码）的兜底，两条路径互不冲突，`sync` 命中的文件如果之后又被 watcher 的防抖事件命中，`reindex_batch` 内部靠 `content_hash` 判断没有实际变化会直接跳过，不会重复做工。

### 2.4 批量事务：保证多文件变化的原子可见性

一次防抖触发或一次 `sync` 调用，不管涉及几个文件，**必须在一个 SQLite 事务里完成**，不要每个文件单独开一个事务：

```python
def reindex_batch(paths: list[str]):
    with conn:  # 一个事务包住整批
        for path in paths:
            _reindex_single_file(conn, path)  # 见上一版文档 2.3 节的实现，逻辑不变
```

原子性在这里有实际意义：比如 Agent 一次性把一个函数从 `a.gd` 挪到 `b.gd`（改了两个文件），如果中间有另一个查询恰好插进来，不用事务包住的话，可能会读到"两个文件都还没有这个函数"或者"两个文件都有这个函数"的中间状态。一个事务保证查询要么看到挪之前的状态，要么看到挪之后的状态，不会看到中间的错误状态。

### 2.5 SQLite 具体配置

```python
conn = sqlite3.connect(".codeindex/index.db")
conn.execute("PRAGMA journal_mode=WAL")       # 读写并发的关键：写者写 WAL 文件，读者读主文件不阻塞
conn.execute("PRAGMA synchronous=NORMAL")     # WAL 模式下 NORMAL 已经足够安全，FULL 会明显拖慢批量写入
conn.execute("PRAGMA busy_timeout=3000")      # CLI 读者遇到 daemon 正在提交大事务时，等最多 3s 而不是立刻报错
```

**唯一写者约束是硬性的**：全局只允许 daemon 一个进程写，CLI 打开连接时显式用只读 URI 防止手滑：

```python
conn = sqlite3.connect("file:.codeindex/index.db?mode=ro", uri=True)
```

### 2.6 CLI 子命令与 schema

| 命令 | 参数 | 返回 |
| --------------------------------------- | -------------- | -------------------- |
| `codeindex find-symbol <name>` | 符号名（精确匹配） | 定义位置列表（文件/行号/所属类/签名） |
| `codeindex call-chain <name> --depth N` | 符号名、追溯深度（默认 3） | 调用者链（递归 CTE 结果） |
| `codeindex class-hierarchy <name>` | 类名 | 祖先链 + 子类列表 |
| `codeindex sync <path>...` | 一个或多个文件路径 | 同步重建结果（成功/失败） |
| `codeindex up` / `status` / `down` | 无 | daemon 生命周期控制 |

所有命令统一 `--json` 输出到 stdout，退出码：`0` 成功、`1` 查无结果、`2` daemon 未运行或索引明显过期（比如 `status` 显示上次成功索引时间和当前时间差太大，提示 Agent 先 `up`）。

### 2.7 数据库 Schema（沿用并微调）

和上一版基本一致，`edges` 表继续坚持"存原始文本、查询时 JOIN 解析"的设计（见上一版理由：动态类型语言强行做静态解析会产生错误的 FK，而且会让增量更新出现级联失效问题）。唯一补充：`files` 表加一列 `last_synced_by`（`watcher` 或 `sync_cmd`），纯粹方便你调试时区分一条记录是被动 watcher 更新的还是 Agent 主动 sync 更新的。

### 2.8 Agent 怎么知道这些命令怎么用

因为这层完全没有 MCP 工具 schema 帮你把参数约束这件事做掉，**Agent 需要一份可靠的"命令手册"**。最简单的做法是给 CLI 加一个 `codeindex --help` 输出结构化说明，并在系统提示/项目的 CLAUDE.md 一类的引导文件里写清楚"有个 `codeindex` 命令可以查符号定义和调用链，先跑 `codeindex --help` 了解用法"。不需要比这更复杂——这也是纯 Bash 路线相对 MCP 唯一的代价：MCP 有结构化 schema 帮你把参数约束和用法描述都做了，Bash 路线需要你用文档/help 文本承担这部分工作，但对一个命令集就 5 条、参数都很简单的 CLI 来说，这点代价可以忽略。

### 2.9 调试

不需要多说——直接 `sqlite3 .codeindex/index.db "select * from symbols where name='take_damage'"`，或者直接跑 `codeindex find-symbol take_damage` 看输出，两者应该一致。这是这条路线相对 MCP 最大的隐性收益：**没有协议层，出问题永远只有两种可能——SQL 写错了，或者数据没建对**，不存在"工具调用协议哪里出了问题"这第三种复杂度。

---

## 三、Layer 3：自建 Godot MCP —— 仅校验

这一层保留 MCP 形态，因为它需要**真实拉起 Godot 二进制**才能产出 Agent 可用的客观信号。LSP 方案已删除，本层只暴露 `verify` 一个工具。

### 3.1 关键结论：这是静态检验，不是运行时检验

**明确回答你的问题：`verify` 做的是静态分析，不会真的把游戏跑起来。** 它通过 `--check-only` 等 headless 命令复用 Godot 自己的 GDScript 解析器/类型推导前端——也就是"编译时会做的那部分检查"（语法解析、类型推导、静态错误诊断），而不是"运行时才会发生的事"（实例化场景树、调用 `_ready()`/`_process()`、真正执行你的游戏逻辑）。

这和"运行时检验"是完全不同的两件事，运行时检验指的是像 satelliteoflove/godot-mcp 那类工具做的事——真的把场景跑起来、注入输入、观察游戏状态，那需要 DAP（调试器协议）连一个正在跑的游戏进程，依赖真实的渲染/物理循环。**你现在这套设计完全不涉及 DAP，也不需要真的运行场景**。

### 3.2 校验指令工具：把探测好的命令收窄成固定入口

你已经自己探测出一组可靠的 headless 校验命令，**直接把它们做成固定参数的具名工具，不要做成"传任意命令行参数"的通用执行器**——这是好的工具设计，不是偷懒：一个通用的"执行任意 godot 命令"工具会让 Agent 有能力拼出你没测试过、可能触发资源导入报错或其他坑的命令组合；收窄成两三个具名工具，每个背后固定绑定一条你已经验证过的命令行，Agent 只能选、不能改参数拼接方式，行为可预测，出问题也永远能复现（因为命令行本身是常量）：

```python
VERIFY_COMMANDS: dict[str, Callable[[str | None], list[str]]] = {
    # 单文件语法/类型检查——具体 flag 换成你自己探测确认可靠的那一组
    "check_file": lambda path: ["--headless", "--check-only", "--script", path or ""],
    # 全工作区扫描
    "check_workspace": lambda _: ["--headless", "--script", "res://tools/check_all.gd"],
}

async def run_verify(kind: str, target: str | None, godot_binary: str) -> VerifyResult:
    argv = [godot_binary, *VERIFY_COMMANDS[kind](target)]
    # subprocess spawn → collect → exit，带 timeout + killpg
    ...
```

校验命令对应的是**一次性子进程**（spawn → 跑完 → 拿输出 → 退出），每次 `verify` 工具调用都是全新的进程，无状态。

### 3.3 复用你的噪声过滤器

校验子进程的 stdout/stderr 本质是"Godot 引擎产出的、需要从中挑出真正有意义的错误、过滤掉噪音（比如资源未导入产生的假错误、无关的引擎警告）"这件事。把你已有的过滤规则抽成一个独立模块（纯函数，输入原始文本，输出过滤后的结构化结果），`verify` 工具在拿到 `VerifyResult` 后调用它：

```python
def filter_verify_output(stdout: str, stderr: str, command: str, autoload_keys: set[str]) -> ProjectFilterView:
    # 你已有的过滤逻辑搬进来，比如识别并丢弃 "resource not imported" 这类假错误
    ...
```

### 3.4 MCP 工具 schema（最终版，仅一个工具）

```python
class VerifyInput(BaseModel):
    kind: Literal["check_file", "check_workspace"]  # 固定枚举，不接受自由字符串
    target: str | None = None                        # check_file 时必填（文件路径），check_workspace 时忽略
```

这就是 Layer 3 的全部工具表面积——一个工具，匹配你说的"功能表简单"。

### 3.5 调试

校验子进程：因为是固定命令行的一次性调用，直接在终端手动跑一遍 `VERIFY_COMMANDS` 里那条命令，看原始输出和你的过滤器过滤前后的差异，永远可复现。

---

## 四、落地计划（更新版）

| 阶段 | 内容 | 工作量 |
| ------- | --------------------------------------------------------------------------- | --- |
| Day 1 | Layer 1：`.rgignore` 配置 + 确认 Agent 能直接用 Bash 调 `rg --json` | 半天 |
| Day 2-3 | Layer 2：`symbols`/`files` 表 + 全量扫描 + `find-symbol` | 2 天 |
| Day 4 | Layer 2：daemon 化（watcher + 防抖 + WAL）+ `codeindex up/status/down` | 1 天 |
| Day 5 | Layer 2：`edges` 表 + `call-chain`/`class-hierarchy` + `sync` 命令接入 Agent 编辑工具 | 1 天 |
| Day 6 | Layer 3：校验子进程封装 + 接入现有噪声过滤器 + MCP 单工具注册 | 1 天 |

一周左右，三层全部落地，且三层里没有一层是"黑盒调不出问题在哪"——Layer 1 是命令行，Layer 2 是 SQL，Layer 3 出问题时也能拆成"是子进程管理的事"还是"是过滤器逻辑的事"，两条独立可排查的链路。

---

## 五、三层最终形态一览

| 层 | 是否 MCP | 进程模式 | 调用方式 | 状态 |
| ---------------- | -------- | ---------------------------------------- | ------------------- | ------------------ |
| Layer 1 grep | 否 | 一次性子进程 | Agent 直接 Bash | 无状态 |
| Layer 2 结构化索引 | 否 | daemon（写）+ CLI（读）两进程 | Agent 直接 Bash 调 CLI | daemon 有状态，CLI 无状态 |
| Layer 3 校验 | 是（自建，Python） | MCP 进程内按需拉起一次性 Godot 校验子进程 | Agent 走 MCP 工具调用 | 校验子进程无状态 |

---

## 六、`codebase/` 子目录架构 Proposal

范围界定先说清楚：这个目录**只装 Layer 2（CLI + daemon）和 Layer 3（自建 MCP server）的实现代码**，Layer 1 的 grep 不进这个目录——它没有任何专属代码，只是 Agent 系统提示里的一句用法说明加一个 `.rgignore`，不构成一个"实现"，放进来也无处安放。

### 6.1 设计原则：这个目录对外只暴露两个东西

不管内部怎么重构，**外部（Agent、CI 脚本、其他人）只应该依赖两个入口**，内部模块随便动都不该影响外部调用方：

1. `codeindex` / `codeindexd` **两个命令行可执行文件**——Layer 2 的全部对外契约，Agent 通过 Bash 调用。
2. **一个 MCP server 启动入口**（`python -m godot_mcp.server` 或打包后的 `godot-mcp` 命令）——Layer 3 的全部对外契约，Agent 的 MCP 客户端配置指向这一个入口。

目录内部其余所有文件（SQL 查询怎么写、tree-sitter query 怎么组织、噪声过滤器怎么实现）都是实现细节，不应该被外部直接 import 或依赖。这条边界决定了下面的目录划分。

### 6.2 目录结构

```
codebase/
├── README.md                    # 对外契约说明：两个入口是什么、怎么启动、依赖什么环境变量
├── config.example.yaml          # 两个子系统共享的配置模板（见 6.4）
│
├── index/                       # Layer 2：daemon + CLI（Python）
│   ├── pyproject.toml
│   ├── src/codeindex/
│   │   ├── cli.py               # `codeindex` 入口：find-symbol / call-chain / sync / status ...
│   │   ├── daemon.py            # `codeindexd` 入口：拉起 watcher，acquire_singleton_lock
│   │   ├── watcher.py           # DebouncedIndexer（静默期 + 硬上限）
│   │   ├── lockfile.py          # flock 单例锁
│   │   ├── config.py            # 读取 ../config.yaml
│   │   ├── db/
│   │   │   ├── schema.sql       # files / symbols / edges 建表语句，唯一权威来源
│   │   │   ├── connection.py    # WAL/busy_timeout pragma，ro/rw 两种连接工厂函数
│   │   │   ├── writer.py        # reindex_batch，唯一允许写库的模块
│   │   │   └── queries.py       # find_symbol / call_chain（递归 CTE）/ class_hierarchy，唯一允许读库的模块
│   │   └── parsers/
│   │       ├── base.py          # Parser 协议：parse(path, source) -> (symbols, edges)
│   │       ├── gdscript.py      # tree-sitter-gdscript 的 Pass1/Pass2 query
│   │       ├── csharp.py        # tree-sitter-c-sharp
│   │       ├── cpp.py           # tree-sitter-cpp
│   │       └── registry.py      # 扩展名 → parser 的映射表，新增语言只改这一个文件
│   └── tests/
│       ├── fixtures/*.gd .cs .cpp     # 每种语言的最小样例文件
│       ├── test_parsers.py            # 每个 parser 单独测（不需要起 daemon）
│       ├── test_queries.py            # 灌固定数据进内存库，测 SQL 查询逻辑
│       └── test_watcher_debounce.py   # 用 fake clock 测防抖/硬上限的时序，不依赖真实文件系统延迟
│
├── godot_mcp/                   # Layer 3：自建 MCP server（Python）
│   ├── pyproject.toml
│   ├── src/godot_mcp/
│   │   ├── config.py            # 读共享 config.yaml，只取 project_root / godot_binary
│   │   ├── server.py            # MCP server 入口，注册 verify 工具
│   │   ├── verify/
│   │   │   ├── commands.py      # VERIFY_COMMANDS 固定命令行白名单
│   │   │   └── runner.py        # 一次性子进程 spawn/collect/exit
│   │   ├── verify_filter/       # 噪声过滤纯函数包
│   │   └── verify_gate/         # 重试门算法
│   └── tests/
│       ├── test_config.py       # config.py 的纯函数测试
│       ├── test_commands.py     # VERIFY_COMMANDS 白名单回归保护
│       ├── verify_filter/...    # verify_filter 黄金测试
│       └── verify_gate/...      # verify_gate 算法测试
│
└── scripts/
    └── bootstrap.sh             # 一键把两个子系统的依赖都装好（pip install -e / uv sync），本地开发用
```

### 6.3 为什么这样切：三条边界线

- `index/` **和** `godot_mcp/` **平级、互不 import**。两者运行时完全独立进程，唯一的关联是"都在服务同一个 Agent、都在处理同一个 Godot 项目"，没有代码层面的依赖关系，平级放置如实反映了这一点，也方便以后任何一个单独抽出去发布成独立包。
- **每个子系统内部按"谁能写、谁只能读"再切一层**：`index/db/writer.py` 是唯一能写库的模块，`queries.py` 只读；`godot_mcp/verify/commands.py` 是唯一定义"能跑哪些 Godot 命令"的地方。这条边界不是目录美观问题，是延续前面几节反复强调的设计约束（单一写者、固定命令白名单）在代码组织上的直接体现——**看目录结构就能看出谁被允许改状态、谁不被允许**，新人接手不需要读完全部代码就能知道改哪里安全、改哪里危险。
- `parsers/registry.py` **和** `verify/commands.py` **是两个明确标出的"唯一扩展点"**：以后要支持第四种语言，只改 `registry.py` 加一行映射；要新增一条校验命令，只改 `commands.py` 加一个条目。其余代码不应该因为加语言/加命令而被改动，这是为了让"这个系统能力边界在哪"始终可以通过看这两个文件直接回答，不需要 grep 整个代码库找隐藏的分支逻辑。

### 6.4 运行时状态不进这个目录

`index.db`、`daemon.lock`、`ready` 标记这些**运行时产物不放进** `codebase/` **目录里**，而是放在被索引的 Godot 项目根目录下的 `.codeindex/`（和文档 2.x 节的路径一致）。原因：

- `codebase/` 是工具的源码，应该被提交进版本库、可以被复用到任意 Godot 项目；运行时状态是"某一次索引某一个项目"产生的数据，和源码的生命周期完全不同，混在一起会导致 `.gitignore` 规则复杂化，也不方便同一套工具代码同时服务多个项目（比如你有多个 Godot 仓库都想用这套索引，源码只需要一份，运行时状态每个项目各有一份）。
- 两个子系统都需要知道"当前在处理哪个 Godot 项目"，通过一个共享的 `config.yaml`（或环境变量 `CODEBASE_PROJECT_ROOT`）统一指定，`index/` 和 `godot_mcp/` 各自从这个配置读路径，避免两边分别硬编码路径导致后续漂移不一致：

```yaml
# codebase/config.example.yaml —— 实际使用时复制成 config.yaml（gitignore 掉，因人/项目而异）
project_root: /path/to/your/godot/project
index_state_dir: /path/to/your/godot/project/.codeindex
godot_binary: godot4
```

### 6.5 目录层面的对外文档

`codebase/README.md` 只需要回答三件事，不需要展开内部实现（内部实现留给各自子目录自己的 README 或代码注释）：

1. 这个目录暴露的两个入口分别是什么命令、怎么启动。
2. 依赖哪些外部环境（Python 版本、`godot4` 二进制在 PATH 里、`config.yaml` 要先从 example 复制一份）。
3. 指向文档二/三节——真正的设计原理写在这份指南里，`README.md` 不重复，只做"怎么跑起来"这一层的说明，避免两份文档互相漂移不一致。
