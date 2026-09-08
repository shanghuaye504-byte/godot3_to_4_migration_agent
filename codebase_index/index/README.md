# index/ — Layer 2：符号索引（daemon + CLI）

设计原理见 `../design.md` 第二节，本文件只说明本目录的代码组织。

## 角色拆分

| 组件 | 进程模式 | 职责 |
| --- | --- | --- |
| `codeindexd`（daemon） | 长驻、唯一写者 | 持有文件监听器与 SQLite 唯一写连接，增量落库 |
| `codeindex`（CLI） | 无状态、只读 | 每次调用启动→查询→打印 JSON→退出 |

拆开的原因：查询是瞬时行为，索引是必须常驻的行为，两者生命周期不对齐，
塞进一个进程会互相拖累（详见 design.md 2.1）。

## 目录结构与权限边界

```
src/codeindex/
├── cli.py            # codeindex 入口：find-symbol / call-chain / class-hierarchy / sync / up / status / down
├── daemon.py         # codeindexd 入口：acquire_singleton_lock → 全量扫描 → 写 ready → 起 watcher
├── watcher.py        # DebouncedIndexer（静默期 500ms + 硬上限 2000ms）
├── lockfile.py       # flock 单例锁（防并发拉起多个 daemon）
├── config.py         # 读取 ../config.yaml（或 CODEBASE_PROJECT_ROOT 环境变量覆盖）
├── db/
│   ├── schema.sql    # files / symbols / edges 建表语句，schema 唯一权威来源
│   ├── connection.py # WAL / busy_timeout pragma；connect_ro / connect_rw 两种连接工厂
│   ├── writer.py     # reindex_batch —— 唯一允许写库的模块
│   └── queries.py    # find_symbol / call_chain（递归 CTE）/ class_hierarchy —— 唯一允许读库的模块
└── parsers/
    ├── base.py       # Parser 协议：parse(path, source) -> (symbols, edges)
    ├── gdscript.py   # tree-sitter-gdscript
    ├── csharp.py     # tree-sitter-c-sharp
    ├── cpp.py        # tree-sitter-cpp
    └── registry.py   # 扩展名 → parser 映射，新增语言只改这一个文件（明确标出的扩展点）
```

**权限边界（看目录结构即知谁能改状态）：**
- 全系统唯一写者 = daemon 进程；进程内唯一写库模块 = `db/writer.py`
- CLI 必须用 `connection.connect_ro()`（只读 URI），禁止用 `connect_rw()`
- `sync` 命令是例外路径：它绕开防抖、同步重建单文件，因此 CLI 在 sync 子命令下才允许拿写连接

## 配置是什么

`config.yaml` **由用户手填，系统不会生成**。仓库只提交 `config.example.yaml`；第一次用时复制成 `config.yaml` 填自己的 Godot 工程路径（该文件已 gitignore）。
系统自动创建的是 `index_state_dir` 里面的运行时文件（`index.db` / `daemon.lock` / `ready`），那是 daemon 跑起来之后写的。

`config.py` 不扫描代码、不连 Godot，也不写 yaml。它只把用户填的路径读进来、拼出派生路径。
`index/`（Layer 2）和 `godot_mcp/`（Layer 3）读同一份 yaml，避免两边各写一套路径后来对不上。

yaml 里四个字段：

| 字段 | 给谁用 | 含义 |
| --- | --- | --- |
| `project_root` | daemon 扫描 / LSP 工作区根 | 被索引的那个游戏项目目录，不是 `codebase_index/` 自身 |
| `index_state_dir` | daemon / CLI | 运行时产物目录，约定为 `project_root/.codeindex/`（`index.db`、`daemon.lock`、`ready`） |
| `godot_binary` | 仅 Layer 3 | `godot4` 可执行文件，Layer 2 现在不用 |

`db_path` / `lock_path` / `ready_path` 不是 yaml 字段，由 `index_state_dir` 拼出来，调用方不要再手写文件名。
`CODEBASE_PROJECT_ROOT` 可覆盖 `project_root`（CI 里换仓库时不必改 yaml）；此时若 yaml 没写 `index_state_dir`，状态目录跟到新根下的 `.codeindex/`。

## 时序保证

- `codeindex up` 阻塞到 daemon 写出 `.codeindex/ready` 才返回，消除冷启动竞态
- watcher 路径防抖：静默期 500ms，硬上限 2000ms（事件持续不断也强制 flush）
- sync 路径：Agent 编辑工具写完文件后同步调用，"读自己刚写的永远是最新的"
- 一次防抖 flush / 一次 sync，无论几个文件都在单个 SQLite 事务内完成（原子可见性）

## 调试

```bash
sqlite3 .codeindex/index.db "select * from symbols where name='take_damage'"
codeindex find-symbol take_damage --json   # 两者结果应一致
```

没有协议层，出问题只有两种可能：SQL 写错了，或数据没建对。

四张表怎么对应 `player.gd`、`CREATE TABLE` / `REFERENCES` / `CREATE INDEX` / CTE 各是什么意思，
见 `docs/schema_walkthrough.md`（本目录 docs/，gitignore）。`schema.sql` 文件头有一份更短的术语对照。

## 实现顺序

原则：自底向上，每一步都能单独跑通对应测试再往上叠。**不要先写 daemon/CLI**——它们只是把下面这些模块串起来，底层没测过时，进程级问题会和 SQL/解析问题搅在一起。

已经写好、实现时不要改契约的文件：`db/schema.sql`、`parsers/base.py`、`parsers/registry.py`（映射表已填；三个 parser 类可以先空着，`registry` 在 import 时会实例化它们，但 `parse()` 在真正被调用前不会执行）。

### 第 0 步：环境能 import

1. `cd index && uv sync --all-groups`（解释器由 `.python-version` 钉在 3.11，不要用 conda 的 3.13）。
   GDScript grammar 没有独立 PyPI 包，`pyproject.toml` 用 `tree-sitter-language-pack` 提供 gdscript/csharp/cpp 三种 Language。
2. 从 `../config.example.yaml` 复制一份到 `../config.yaml`，把 `project_root` / `index_state_dir` 改成一个真实的小 Godot 项目（或临时空目录）。后续 `config.py` 测的就是读这份文件。
3. 确认 `uv run python -c "import codeindex"` 能过。此时各模块里的 `...` 还不会炸，因为没人调用它们。

### 第 1 步：`config.py`（无内部依赖）

填：`Config.db_path` / `lock_path` / `ready_path` 三个 property，以及 `load_config()`。

- 路径约定：`index.db`、`daemon.lock`、`ready` 都拼在 `index_state_dir` 下。
- `CODEBASE_PROJECT_ROOT` 环境变量覆盖 yaml 里的 `project_root`；`index_state_dir` 缺省时用 `project_root / ".codeindex"`。
- 注意骨架里 `_CONFIG_SEARCH_PATH` 用了 `parents[4]`，实际 `config.yaml` 在 `codebase_index/` 根下，实现时改成 `parents[3]`（`codeindex/` → `src/` → `index/` → `codebase_index/`）。
- 测试：`tests/test_config.py`（给临时 yaml，不读仓库里的 `config.yaml`）。

调通标准：`uv run pytest tests/test_config.py` 全绿。

### 第 2 步：`db/connection.py`（只依赖 schema.sql）

填：`_apply_pragmas()`、`connect_rw()`、`connect_ro()`。

- `connect_rw`：建父目录、`sqlite3.connect`、打 pragma、`executescript(schema.sql)`。
- `connect_ro`：URI `file:{path}?mode=ro`，只设 `busy_timeout`，**不要**再跑 schema（只读库跑 DDL 会失败）。
- 测试：`tests/test_connection.py`（临时目录建库，不读 `config.yaml`）。
- 导读：`docs/connection_walkthrough.md`。

调通标准：`uv run pytest tests/test_connection.py` 全绿。

### 第 3 步：解析器（不需要数据库、不需要 daemon）

顺序：**先 GDScript，再 C#，再 C++**。主路径是 `.gd`，后两种语言先能过 fixture 即可，tree-sitter 节点名和 grammar 对不上时在这一步当场调，不要拖到 writer 里才发现。

1. 填 `parsers/gdscript.py`：`_language()` 懒加载 + `GdscriptParser.parse()`。
2. 填 `tests/test_parsers.py` 里 GDScript 那两组断言（`fixtures/player.gd` 的符号/边 + 语法错误抛 `SyntaxError`），跑通。
   **已完成**：`uv run pytest tests/test_parsers.py` 覆盖上述两组。真实 grammar 节点名是 `class_name_statement` / `const_statement` / `attribute_call`，以 parser 内注释为准。
3. 填 `parsers/csharp.py`，补 C# 断言，跑通 `fixtures/Player.cs`。
   **已完成**：`class_declaration` / `invocation_expression`；基类取 `base_list` 第一个 identifier。
4. 填 `parsers/cpp.py`，补 C++ 断言，跑通 `fixtures/native.cpp`（declarator 剥层）。
   **已完成**：`class_specifier` / `call_expression`；`PlayerNative::die` 剥 `qualified_identifier` 得到 `die`。

`registry.py` 不用改。如果某个 parser 的 tree-sitter 节点类型和 docstring 假设不一致，只改该 parser 内部，不要改 `ParseResult` 字段。

调通标准：`uv run pytest tests/test_parsers.py` 全绿（三种语言 + 语法错误路径）。此时还没有任何 SQLite 写入。

### 第 4 步：`db/writer.py`（连接 + 解析器第一次会合）

先填 `_reindex_single_file()`，再填 `reindex_batch()`。

`_reindex_single_file` 按 docstring 五条分支一次写齐，不要拆事务：

1. `registry.get_parser` 为 `None` → `skipped`
2. 文件不存在 → `DELETE FROM files WHERE path=?`（CASCADE 清符号）→ `reindexed`
3. hash 与库中一致 → `skipped`
4. hash 变了或新文件 → upsert `files`，先删该 `file_id` 的 symbols/edges/classes，再 parse
5. `parse()` 抛异常 → 保留 `files` 行、符号表为空 → `failed`

`reindex_batch` 必须是 `with conn:` 包住整个 for 循环（一个事务）。

测试：在 `tests/test_queries.py` 里先写 **writer 幂等那条**（同一文件连续 `reindex_batch` 两次，第二次 `skipped == 1`），以及一条失败路径（喂半截 `.gd`，`failed == 1` 且 `files` 行还在、`symbols` 为空）。

**已完成**：`uv run pytest tests/test_queries.py` 覆盖幂等 / 语法失败留户口 / `player.gd` 符号与边 / 未知扩展名 / 内容变更换符号 / 文件删除 CASCADE。导读：`docs/writer_walkthrough.md`。本步 **没有** 实现 `queries.py` 里的 SQL（那是第 5 步）。

调通标准：对 `fixtures/player.gd` 落库后，用 `sqlite3` 能看到 `Player` / `take_damage` / `_die` 和对应 `edges`。

### 第 5 步：`db/queries.py`（只读 SQL，可用内存库灌固定数据）

这一步**不要**依赖 writer 产出的真实解析结果，用 `tests/test_queries.py` 里手工 INSERT 的固定行测 SQL，避免 parser 细节污染查询逻辑。

填的顺序：

1. `find_symbol()` —— 精确匹配，JOIN `files`，按 path/line 排序。
2. `status()` —— `COUNT` + `MAX(indexed_at)`，给后面 CLI `status` 用。
3. `call_chain()` —— 递归 CTE，`edges.to_name` 查询期 JOIN，`depth` 截断。
4. `class_hierarchy()` —— 祖先链 CTE + `base_name = ?` 查子类。

对应测试也按这个顺序往 `test_queries.py` 里填。`call_chain` 的 fixture 语义是 `_die ← take_damage ← hurt`。

**已完成**：`uv run pytest tests/test_queries.py` 里 queries 四组测例用内存库手工 INSERT，不调 parser。导读：`docs/queries_walkthrough.md`。

调通标准：`uv run pytest tests/test_queries.py` 全绿。至此 **「索引能写、能查」这条数据通路闭环了**，还没有任何常驻进程。

### 第 6 步：`watcher.py`（纯时序，与文件系统无关）

填 `DebouncedIndexer`：`on_file_changed` / `_flush` / `flush_now`。`clock` 可注入；`threading.Timer` 必须能被测试 monkeypatch。

然后一次性写完 `tests/test_watcher_debounce.py` 两条：

- 静默期：500ms 内连续事件合并成 **一次** flush，集合包含全部 path。
- 硬上限：事件间隔 400ms、永远等不到静默期时，2000ms 强制 flush，且携带全部 pending。

调通标准：`uv run pytest tests/test_watcher_debounce.py` 全绿。本步不碰 SQLite。

**已完成**：静默期合并 + 硬上限携带全部 pending；`clock` 可注入，`threading.Timer` 可 monkeypatch。导读：`docs/watcher_walkthrough.md`。

### 第 7 步：`lockfile.py`（进程级，但仍很薄）

填 `acquire_singleton_lock()`：`O_CREAT|O_RDWR` → `LOCK_EX|LOCK_NB` → 写入 pid → 返回 fd。抢不到则 stderr 提示并以退出码 1 退出。

测法：同一 `lock_path` 上起两个短脚本，第二个必须失败。fd 必须被调用方持有到进程退出（不要在函数里 close）。

调通标准：手动跑两次抢锁，第二次立刻退出；第一个进程结束后第二次能抢到。

**已完成实现**：`acquire_singleton_lock` 按 docstring 五步落地。本步 **没有** pytest 自动化；用两个终端手动验证（导读：`docs/lockfile_walkthrough.md`）。

### 第 8 步：`daemon.py`（第一次把写路径做成进程）

填的顺序：

1. `_iter_source_files(root)`：目录排除（`.godot` / `.import` / `.git` / `__pycache__`），扩展名交给 `registry.get_parser`。
2. `_full_scan(conn, project_root)`：收集文件列表，一次 `writer.reindex_batch(..., synced_by="watcher")`。
3. `main()` 严格按模块 docstring 四步：抢锁 → 全量扫描 → 写 `ready` 时间戳 → `watchfiles.watch` 循环把变化喂给 `DebouncedIndexer`。SIGTERM/SIGINT 里 `flush_now`、commit、删 `ready`、关连接。

本步先不要走 CLI：直接 `uv run python -m codeindex.daemon`（需已有 `config.yaml`）。看 `.codeindex/ready` 是否出现、`index.db` 里是否有符号，再改一个 `.gd` 等最多 2 秒看是否增量更新。Ctrl+C 后 `ready` 应消失。

调通标准：对 `config.yaml` 指向的项目，daemon 能独立跑完首次扫描并响应一次文件改动。此时查询还只能用 `sqlite3` 手查。

**已完成实现**：`_iter_source_files` / `_full_scan` / `main` 四步启动 + 信号处理。本步 **没有 pytest**；手测步骤见 `docs/daemon_walkthrough.md`。`watchfiles` 的 `debounce` 设为 1ms，500/2000 仍由 `DebouncedIndexer` 负责。

### 第 9 步：`cli.py` —— 先生命周期，再查询，最后 sync

`cli.py` 不要一次写完七个子命令。按下面三段，每段都能在终端敲通再写下一段。

**9a. 脚手架**

- `build_parser()`：七个子命令的 argparse（`--help` 就是 Agent 手册，help 文本按 docstring 写清楚）。
- `_emit()`：stdout JSON + 返回退出码。
- `main()`：`load_config` 失败 → 退出码 2；否则按 command dispatch。

此时子命令函数可以先返回固定 JSON，确认 `uv run codeindex --help` 和错误配置路径工作。

**9b. `up` / `status` / `down`（依赖 daemon + lockfile）**

- `_daemon_running()`：读 lock 文件 pid，`os.kill(pid, 0)` 探活。
- `cmd_up`：已在跑则直接返回；否则 `Popen(..., start_new_session=True)` 拉起 `python -m codeindex.daemon`，**轮询 `ready` 出现再返回**，120s 超时退出码 2。
- `cmd_status`：未运行退出码 2；否则 `connect_ro` + `queries.status`，超时 `_STALE_SECONDS` 标 `stale`。
- `cmd_down`：对 pid 发 SIGTERM。

调通标准：

```bash
uv run codeindex up
uv run codeindex status
uv run codeindex down
```

`up` 返回前 `ready` 必须已存在；`status` 的 `files`/`symbols` 与 sqlite 手查一致。

**9c. 三个只读查询**

- `_require_ready()`：daemon 未跑或 db 不存在 → 退出码 2。
- `cmd_find_symbol` / `cmd_call_chain` / `cmd_class_hierarchy`：一律 `connect_ro`，空结果退出码 1。

调通标准：对已知符号 `codeindex find-symbol take_damage` 退出码 0，JSON 与 `sqlite3` 查询一致；查不存在的名字退出码 1。

**已完成实现**：七个子命令一次写齐（argparse / `_emit` / 探活 / 三个查询 / `sync`）。
`up` 用 `Popen(start_new_session=True)` 拉 `python -m codeindex.daemon`，轮询 `ready` 最多 120s。
查询一律 `connect_ro`；只有 `sync` 走 `connect_rw`。导读：`docs/cli_walkthrough.md`。
`--json` 挂在子命令上（输出本来就是 JSON，旗只为兼容文档写法）。

### 完成判定（index/ 整包）

全部满足才算 Layer 2 骨架填完，再去动 `godot_mcp/`：

- `uv run pytest tests/` 三类测试全绿（parsers / queries / watcher）。
- `codeindex up` → `find-symbol` / `call-chain` / `class-hierarchy` → `sync` → `down` 这条命令链在真实项目上能走通。
- 同一时刻起第二个 daemon 会因 flock 立刻退出。
- 查询 CLI 在 daemon 没起来时退出码为 2，而不是 Traceback。
