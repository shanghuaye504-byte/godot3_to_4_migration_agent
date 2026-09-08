# Layer 2 索引库：对话里真正学会的那些点

> 课堂笔记，不是 schema 权威说明。表结构以 [`codebase_index/index/src/codeindex/db/schema.sql`](../codebase_index/index/src/codeindex/db/schema.sql) 为准；打开库的代码在 [`connection.py`](../codebase_index/index/src/codeindex/db/connection.py)。
>
> 用 `player.gd` 把表填成行的走读在 [`codebase_index/index/docs/schema_walkthrough.md`](../codebase_index/index/docs/schema_walkthrough.md)（该目录 `docs/` gitignore）。本文只收「当时问过、容易再忘」的概念。

背景：`codeindex` 是常驻 daemon（唯一写者）+ 无状态 CLI（只读）。库文件在被索引 Godot 项目的 `.codeindex/index.db`，不在本仓库源码树里。

---

## 1. 配置和库是两件事

`config.yaml` **用户手填**，系统不会生成。仓库只交 `config.example.yaml`。系统自动创建的是 yaml 指向的目录里的运行时文件：`index.db`、`daemon.lock`、`ready`。

`config.py` 只拼路径（`project_root` → `.codeindex/` → `index.db`）。`connection.py` 不读 yaml，只接收已经拼好的 `db_path`，把它变成一条 SQLite 会话。

---

## 2. 四张表：一个户口 + 三种关系

不要把库理解成「一张符号大宽表」。三种 CLI 问的是三种不同形状的问题：

| 问题 | 关系 | 表 |
| --- | --- | --- |
| `take_damage` 定义在哪个文件第几行？ | 名字 → 定义位置 | `symbols`（JOIN `files` 换路径） |
| 谁调用了 `_die`？再上一层是谁？ | 调用箭头 | `edges` |
| `Player` 的父类 / 子类是谁？ | 继承箭头 | `classes` |

`files` 只是源文件户口。子表全部 `REFERENCES files(id) ON DELETE CASCADE`：删掉 `player.gd` 那一行，它下面的符号、调用边、继承边一起消失，避免孤儿。

**`edges` / `classes` 按箭头读，不要当第二份符号清单。**

```
from_symbol  ──call──►  to_name          take_damage → _die
name         ──extends──►  base_name     Player → CharacterBody2D
```

「谁调用了 `_die`」= `WHERE to_name='_die'`，读出 `from_symbol`。  
另一端存**源码原文**，不存 `symbols.id`：`queue_free`、`CharacterBody2D` 是引擎 API，本仓库往往没有定义行，边仍然合法。绑错外键再 CASCADE，会误删别的文件的边。

模糊搜索不是这张库的事（那是 `rg` 和 Layer 3 LSP）。这里三条 CLI 都是等值查找，所以只给 WHERE 用到的列建 `CREATE INDEX`。

---

## 3. 第一次碰到的 SQL 词

- **`CREATE TABLE`**：建表。列 = 名字 + 类型 + 约束。`IF NOT EXISTS` 让 daemon 每次打开库再跑一遍也不报错。
- **`INTEGER PRIMARY KEY`**：这一行的身份证（SQLite 的 rowid）。
- **`REFERENCES files(id)`**：外键，这格必须是 `files` 里已有的 id。
- **`ON DELETE CASCADE`**：这里的 `ON` 是「父行被删时子行怎么处理」。和查询里的 `JOIN ... ON` 不是同一个 `ON`。
- **`CREATE INDEX ... ON 表(列)`**：给某一列做目录，`WHERE 列=?` 不用全表扫。这里的 `ON` 是「索引建在哪」。
- **`JOIN 表 ON 条件`**：查询时才出现，schema 里没有。两张表按条件把行夹在一起（用 `file_id` 把路径拼回来）。

**CTE**（`WITH 名字 AS (SELECT ...)`）是查询写法，不是第五张业务表。给子查询起个临时名。`WITH RECURSIVE` 让临时表引用自己：call-chain / 祖先链一层层往上爬，`--depth` 截断。schema 里不会 `CREATE TABLE callers`。

---

## 4. 打开库：`conn`、URI、两套 timeout

`conn` 不是数据库文件，也不是一张表。它是 Python 里的 **`sqlite3.Connection`：对着已打开的 `index.db` 的会话句柄**。可以想成电话接通后的那条通话。真正开文件、管锁、跑 SQL 的是下面的 SQLite C 库；Python 对象只是包装。`close()` 挂断会话，文件还在。数据大部分仍在磁盘，用到的页才进缓存。

两条工厂，用函数名守「谁能写」：

- `connect_rw`：daemon 和 `codeindex sync`。建目录、打 PRAGMA、`executescript(schema.sql)`。
- `connect_ro`：查询 CLI。URI `mode=ro`，写会被拒。不能再跑 schema（`CREATE TABLE` 也是写）。

**`executescript`**：一次跑多条 SQL（整份 schema）。`execute` 一次只能一条。

**为什么只读必须用 URI，读写却不用**

| | 参数被当成什么 | 能不能写 `?mode=ro` |
| --- | --- | --- |
| 普通路径（`rw` 默认） | 文件名 | 不能，问号会变成文件名的一部分 |
| URI（`ro`） | `file:` 地址 + `?` 参数 | 能 |

`uri=True` 是 **Python** 的开关：「请按 URI 解析这段字符串」。  
`?mode=ro` 是 **SQLite** 的开关：「这条连接只读」。  
少了 `uri=True`，Python 会去打开一个名叫 `file:///.../index.db?mode=ro` 的文件，只读不会生效。路径用 `Path.as_uri()`，避免空格和 Unix 绝对路径斜杠数量的坑。

**两个 timeout 作用在不同阶段（都是 3 秒，不是两套无关的策略）**

- `connect(..., timeout=3)`：单位秒。**建立连接这一下**若库忙，最多等 3 秒。
- `PRAGMA busy_timeout=3000`：单位毫秒。**连接已打开之后每一次 SQL** 若拿不到锁，再等最多 3 秒。

只设其中一个，另一段仍可能瞬间 `database is locked`。`rw` 的语句级超时在 `_apply_pragmas` 里；`ro` 不跑那套 PRAGMA，所以单独 `execute` 一句。

`check_same_thread=False`：Python sqlite3 默认「谁 connect 谁用」。daemon 全量扫描在主线程，防抖 flush 在 Timer 线程，必须关。关掉 ≠ 两个写者同时写；只是允许同一条连接跨线程递一下。

---

## 5. PRAGMA、WAL、为什么已经 WAL 还要 busy_timeout

**PRAGMA** 是 SQLite 的开关语句，不是查表。`SELECT` 问表里有什么；`PRAGMA` 问这个库怎么运行。每个新连接都要再设一遍（`foreign_keys` 默认关，不设则 schema 里的 CASCADE 不会生效）。

**WAL = Write-Ahead Log（预写日志）**。写者往旁边的 `index.db-wal` 追加，读者继续读 `index.db` 上一份完整快照。常见情况：daemon 重建符号时，CLI 仍能读，且不会读到改到一半。checkpoint 把 wal 合并回主库后，`-wal` 文件可能消失——判断是不是 WAL 看 `PRAGMA journal_mode`，不要看那个文件还在不在。

WAL **不是**「任何时候都完全不等」。它保证读者 vs 一个写者平时不堵；仍然堵的是：

1. **写者 vs 写者**（对本项目最要紧）：WAL 同一时刻仍只允许一个写者。`codeindex sync` 也走 `connect_rw`，可能和 daemon 的 `reindex_batch` 撞车。
2. checkpoint 需要短暂独占。
3. `index.db-shm` 上极短的内部锁。

对 **`connect_ro` 来说冲突概率很低**（WAL 就是为这个场景服务的）。timeout 是便宜的保险，避免 CLI 在一次 checkpoint 上闪崩，不是因为读写天天打架。3 秒来自设计文档的经验值：一次批量重建通常远短于 3 秒；再长会像挂死；等满仍忙应报错，多半是 daemon 卡死或磁盘有问题。

---

## 6. `synchronous=NORMAL`：没放宽「事务要么全成要么全不成」

`synchronous` 是 PRAGMA 的**名字**；`NORMAL` / `FULL` / `OFF` 是它的**取值**。不要说成「NORMAL 模式和 synchronous 模式」。

它管的不是原子性，而是 **commit 已经返回之后突然掉电，最后几笔还在不在磁盘上**（持久性）。`fsync` = 强迫操作系统把缓存刷到磁盘。

| | 含义 | `NORMAL` 会不会破坏 |
| --- | --- | --- |
| 原子性 / 一致性 | 一批 INSERT 要么全在要么全不在；查询看不到挪函数挪到一半 | **不会**（WAL + 单事务 `reindex_batch`） |
| 持久性 | 进程已 commit，机器立刻断电，这笔还在不在 | **可能丢掉最后几笔已提交、但还没 checkpoint / 还在 OS 缓存里的事务** |

WAL 下 `FULL` = 每次 commit 都 `fsync` WAL，慢，掉电也尽量不丢。`NORMAL` = 平时提交写到 OS 缓存，checkpoint 时才认真刷盘。索引丢了可以按 `content_hash` 再扫，换批量写入速度；银行账户不能选这个。`OFF` 有损坏风险，不用。

---

## 7. 和本项目的对应关系（记这张图就够）

```
用户手填 config.yaml
        │
        ▼
  cfg.db_path = project/.codeindex/index.db
        │
        ├─ connect_rw  →  daemon / sync     建表、WAL、可写
        └─ connect_ro  →  find-symbol 等    URI mode=ro

磁盘：index.db +（有时）index.db-wal / index.db-shm
查询：symbols / edges / classes 三种箭头或定义，走对应 INDEX
```

出问题仍然只有两类：SQL 写错了，或数据没建对。没有第三层「工具协议」。

---

## 8. 第 4–5 步问答（writer / queries）

路径拆分、`(rel,)` 元组、hash 与 parse 必须同一份文本、整文件重建、`lastrowid`、
`description`/`fetchall`/`row_factory`、JOIN/UNION 与复杂度、计划器如何选索引、
两条递归 CTE、同名列不是笛卡尔积重合、`sync` 与 watcher 写锁排队（不是同时写同一行）：

见 [`codebase_index/index/docs/sqlite_qna.md`](../codebase_index/index/docs/sqlite_qna.md)（gitignore）。

