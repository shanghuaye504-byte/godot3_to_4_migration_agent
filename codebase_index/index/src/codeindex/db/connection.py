"""SQLite 连接工厂（design.md 2.5）。

本模块不查符号、不跑 parser。它只负责「怎么打开 index.db」。

两条入口，对应两个进程角色（看函数名就能知道谁允许改库）：

    connect_rw(path)  读写。仅 daemon，以及 CLI 的 sync 子命令。
                      第一次打开时执行 schema.sql，把四张表建出来。
    connect_ro(path)  只读。CLI 的 find-symbol / call-chain / class-hierarchy / status。
                      用 URI mode=ro，INSERT/UPDATE/DELETE 会被 SQLite 拒绝。

磁盘上实际是一组文件，都在 index_state_dir 下（路径由 config.py 拼好）：

    index.db          主库（表数据）
    index.db-wal      WAL 日志。写者往这里追加。连接 close 且 checkpoint 干净后可能被收掉，
                      不要用「这个文件在不在」判断是不是 WAL，要用 PRAGMA journal_mode。
    index.db-shm      WAL 的共享内存索引（SQLite 自己管）

PRAGMA 是 SQLite 的开关，不是 SQL 表。每个新连接都要重新设一遍
（foreign_keys 尤其如此：SQLite 默认关，不设则 ON DELETE CASCADE 不会生效）。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# 和本文件同目录的 schema.sql。connect_rw 建库时整份执行，是表结构的唯一入口。
_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# 与 design.md 2.5 一致：读者碰到写者正在提交时，最多等这么久，而不是立刻报 locked。
_BUSY_TIMEOUT_MS = 3000


def _apply_pragmas(conn: sqlite3.Connection, *, writer: bool) -> None:
    """给一条已经打开的连接打上本项目约定的开关。

    journal_mode=WAL
        默认 DELETE 模式是写者改主文件时读者必须等。
        WAL = Write Ahead Log：写者往 index.db-wal 追加，读者继续读 index.db 快照，
        这是 daemon（写）和 CLI（读）能同时跑的关键。
        这条 PRAGMA 会返回当前模式；WAL 一旦写入文件头，之后的连接会跟过来。

    synchronous=NORMAL
        WAL 下 NORMAL 在 checkpoint 时 fsync，崩溃最多丢最后一个事务，表不会坏。
        FULL 每个事务都 fsync，批量重建会明显变慢，这里不需要。

    busy_timeout=3000
        写者提交大事务时库是忙的。读者等到 3 秒；超时才抛 OperationalError。
        单位是毫秒。Python sqlite3.connect(timeout=...) 是另一层等待，下面一并设成 3 秒。

    foreign_keys=ON（仅写者）
        SQLite 每个连接默认关闭外键。不打开的话 schema 里的
        REFERENCES ... ON DELETE CASCADE 只是注释，删 files 行不会清子表。
        只读连接不会 DELETE，不必开。
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    if writer:
        conn.execute("PRAGMA foreign_keys=ON")


def connect_rw(db_path: Path) -> sqlite3.Connection:
    """打开（或创建）读写连接。调用方用完必须 close。

    谁可以调：daemon 进程、CLI 的 `codeindex sync`。其它 CLI 子命令禁止走这里。
    本函数不检查调用方身份，靠代码审查和「查询只 import connect_ro」来守这条边界。

    步骤：
      1. 确保父目录存在（.codeindex/ 可能还没建过）
      2. 打开主文件；timeout=3s 与 busy_timeout 对齐
      3. check_same_thread=False：daemon 的 DebouncedIndexer 用 Timer 线程 flush，
         和启动时的全量扫描不在同一线程。同一时刻仍只有一个写者。
      4. 打 PRAGMA
      5. 执行 schema.sql（CREATE TABLE IF NOT EXISTS，重复打开是幂等的）
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(db_path),
        timeout=_BUSY_TIMEOUT_MS / 1000,
        check_same_thread=False,
    )
    _apply_pragmas(conn, writer=True)
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def connect_ro(db_path: Path) -> sqlite3.Connection:
    """打开只读连接。库必须已经存在（daemon 第一次 connect_rw 之后）。

    用 URI `file:.../index.db?mode=ro`，uri=True 才让 SQLite 解析问号后的参数。
    路径走 Path.as_uri()，得到 file:///abs/path，避免空格和「斜杠数量」踩坑。

    故意不执行 schema.sql：只读连接跑 CREATE TABLE 会失败。
    也故意不设 journal_mode——库文件头已经是 WAL，读者跟着读即可。
    """
    uri = db_path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(
        uri,
        uri=True,
        timeout=_BUSY_TIMEOUT_MS / 1000,
    )
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    return conn
