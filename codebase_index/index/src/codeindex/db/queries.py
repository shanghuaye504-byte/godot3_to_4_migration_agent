"""唯一允许读库的模块：CLI 查询命令背后的 SQL（design.md 2.6 / 2.7）。

所有函数只 SELECT，不 INSERT / UPDATE / DELETE。调用方应传入
``connection.connect_ro`` 的连接；本模块不检查连接是不是只读，靠代码审查守这条边界。

四条入口和 CLI 一一对应：

    find_symbol        这个名字定义在哪
    status             库里有多少文件/符号、上次索引何时
    call_chain         谁调用了这个名字，再往上爬 depth 层
    class_hierarchy    这个类的祖先链 + 直接子类

edges.to_name / classes.base_name 存的是源码原文，不是 symbols.id。
「解析」发生在查询期：用字符串去对 ``symbols.name`` / ``classes.name``，对上就展开，对不上就停。
这是设计，不是漏了外键——引擎 API（queue_free、CharacterBody2D）在本仓库里往往没有定义行。
"""

from __future__ import annotations

import sqlite3
from typing import Any


def _fetch_dicts(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """跑一条 SELECT，把每一行收成 ``列名 → 值`` 的 dict。

    功能：queries 对外返回 JSON 友好的结构，不把 sqlite3 的 tuple/Row 漏给 CLI。
    不改 ``conn.row_factory``——那会动调用方的连接状态，读写测试共用连接时会互相踩。查询操作不应该改变连接状态。
    """
    cur = conn.execute(sql, params)
    columns = [col[0] for col in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def find_symbol(conn: sqlite3.Connection, name: str) -> list[dict[str, Any]]:
    # SCENE_INDEX_TODO(step3-find-symbol): 见 codebase_index/NEXT_STEP.md 第 7 节开头的「标记」说明。
    # 实现时在返回里追加场景引用。下面这条查询的列保持不动，matches[].line 仍是 0-based。
    """精确匹配符号名，返回定义位置列表（文件 / 行号 / 所属类 / 签名）。

    功能：回答「``take_damage`` 写在哪个文件第几行」。
    ``WHERE s.name = ?`` 走 ``idx_symbols_name``；等号是精确匹配，不是 LIKE 子串。
    ``JOIN files`` 把 ``file_id`` 换成路径——symbols 表里只有整数外键，没有路径字符串。

    同名可以有多行（两个文件都定义了 ``take_damage``，或同文件重载）。
    ``ORDER BY f.path, s.line`` 让输出稳定，CLI / 测试可以对着列表断言。

    查无结果返回空列表，不抛异常；退出码 1 是 CLI 的事。
    """
    return _fetch_dicts(
        conn,
        """
        SELECT
            f.path AS path,
            s.name AS name,
            s.kind AS kind,
            s.line AS line,
            s.end_line AS end_line,
            s.class_name AS class_name,
            s.signature AS signature
        FROM symbols AS s
        JOIN files AS f ON f.id = s.file_id
        WHERE s.name = ?
        ORDER BY f.path, s.line
        """,
        (name,),
    )


def status(conn: sqlite3.Connection) -> dict[str, Any]:
    """索引概况：文件数、符号数、上次索引时间。

    功能：给以后 CLI ``codeindex status`` 判断「库是空的 / 索引是否过期」。
    ``MAX(indexed_at)`` 是 files 里最晚那一次重建的 epoch 秒；空库时 SQLite 对空集求 MAX 得到 NULL，
    Python 这边是 ``None``。``files`` 计数包含 parse 失败只留下户口、子表为空的那些行。
    """
    files_n, symbols_n, last_indexed_at = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM files) AS files,
            (SELECT COUNT(*) FROM symbols) AS symbols,
            (SELECT MAX(indexed_at) FROM files) AS last_indexed_at
        """
    ).fetchone()
    return {
        "files": files_n,
        "symbols": symbols_n,
        "last_indexed_at": last_indexed_at,
    }


def call_chain(conn: sqlite3.Connection, name: str, depth: int = 3) -> list[dict[str, Any]]:
    """调用者链：谁调用了 ``name``，再把调用者当下一层的 ``to_name`` 往上爬。

    功能：回答「谁调用了 ``_die``？谁又调用了那个调用者？」。
    顺着 schema 里的箭头 **反着** 走::

        take_damage  ──call──►  _die        edges.to_name = '_die'
        hurt         ──call──►  take_damage 再拿 take_damage 当 to_name

    递归 CTE（``WITH RECURSIVE``）形状：

      锚点     ``WHERE to_name = ? AND kind = 'call'``  → depth=1 的直接调用者
      递归步   ``e.to_name = 上一层.from_symbol``，且 ``depth < ?``
      这就是查询期解析：对的是字符串，不是 ``symbols.id``。
      ``kind='call'`` 把 extends / preload 边排除在外。

    ``UNION ALL`` 而不是 ``UNION``：同一调用者两处调用站点（不同 line）都要保留；
    ``UNION`` 会按列去重，丢掉第二次调用。深度上限负责截断，也防止 A↔B 循环把 CTE 跑死。

    ``LEFT JOIN symbols``：在同一文件里找 ``from_symbol`` 的定义行（展示用 class_name / signature）。
    找不到（只在边里出现、库里没有 func 行）仍然保留这条边——调用关系本身是合法的。

    ``depth < 1`` 时没有「第 0 层调用者」，直接返回空列表。
    """
    if depth < 1:
        return []
    return _fetch_dicts(
        conn,
        """
        WITH RECURSIVE callers(
            from_symbol, to_name, file_id, line, depth
        ) AS (
            SELECT e.from_symbol, e.to_name, e.file_id, e.line, 1
            FROM edges AS e
            WHERE e.to_name = ? AND e.kind = 'call'

            UNION ALL

            SELECT e.from_symbol, e.to_name, e.file_id, e.line, c.depth + 1
            FROM edges AS e
            INNER JOIN callers AS c ON e.to_name = c.from_symbol
            WHERE e.kind = 'call' AND c.depth < ?
        )
        SELECT
            c.from_symbol AS name,
            c.depth AS depth,
            f.path AS path,
            c.line AS line,
            c.to_name AS to_name,
            s.class_name AS class_name,
            s.signature AS signature
        FROM callers AS c
        JOIN files AS f ON f.id = c.file_id
        LEFT JOIN symbols AS s
            ON s.name = c.from_symbol AND s.file_id = c.file_id
        ORDER BY c.depth, f.path, c.line
        """,
        (name, depth),
    )


def class_hierarchy(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    """祖先链 + 直接子类列表。

    功能：回答「``Player`` 往上 extends 到谁」以及「谁又 extends 了 ``Player``」。

    祖先链（递归 CTE）：
      锚点     ``classes.name = ?``，读出这一行的 ``base_name``（原文，可能是引擎类）
      递归步   ``classes.name = 上一层.base_name`` —— 查询期字符串匹配
      每一层的 ``base_name`` 就是一个祖先。引擎类（CharacterBody2D）在 classes 里没有行，
      JOIN 下一层失败，链在这里自然停，但 ``base_name`` 本身仍作为最后一截祖先返回。
      ``depth < 32`` 防止 A extends B extends A 的坏数据把 CTE 跑死。

    子类（普通 SELECT，不递归）：
      ``WHERE base_name = ?`` 走 ``idx_classes_base``，只列直接子类。
      问引擎类 ``CharacterBody2D`` 时，它自己可能不在 classes 里，但子类查询仍然有结果。

    返回结构始终是 dict，查不到也是空列表，不返回 None。
    """
    ancestors = _fetch_dicts(
        conn,
        """
        WITH RECURSIVE walk(
            cls_name, base_name, file_id, line, depth
        ) AS (
            SELECT name, base_name, file_id, line, 0
            FROM classes
            WHERE name = ?

            UNION ALL

            SELECT c.name, c.base_name, c.file_id, c.line, w.depth + 1
            FROM classes AS c
            INNER JOIN walk AS w ON c.name = w.base_name
            WHERE w.base_name IS NOT NULL AND w.depth < 32
        )
        SELECT
            w.base_name AS name,
            f.path AS path,
            parent.line AS line
        FROM walk AS w
        LEFT JOIN classes AS parent ON parent.name = w.base_name
        LEFT JOIN files AS f ON f.id = parent.file_id
        WHERE w.base_name IS NOT NULL
        ORDER BY w.depth
        """,
        (name,),
    )
    subclasses = _fetch_dicts(
        conn,
        """
        SELECT
            c.name AS name,
            f.path AS path,
            c.line AS line,
            c.base_name AS base_name
        FROM classes AS c
        JOIN files AS f ON f.id = c.file_id
        WHERE c.base_name = ?
        ORDER BY f.path, c.line
        """,
        (name,),
    )
    return {"name": name, "ancestors": ancestors, "subclasses": subclasses}
