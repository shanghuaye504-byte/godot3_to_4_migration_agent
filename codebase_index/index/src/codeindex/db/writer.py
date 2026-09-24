"""唯一允许写库的模块（design.md 2.4 / 6.3）。

parser 只产出 ParseResult（内存对象）。本模块把它变成 files / symbols / edges / classes 四张表里的行。
查询模块 queries.py 不准 import 本文件。

一次防抖 flush 或一次 sync，无论几个文件，都在 **一个** SQLite 事务里完成：
读者要么看到整批之前，要么之后，不会看到「函数从 a.gd 挪到 b.gd 挪到一半」。

幂等：content_hash 没变就 skipped。sync 刚写过的文件，watcher 稍后再命中也不会重解析。
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path

from ..parsers import registry
from ..parsers.base import ParseResult


def reindex_batch(
    conn: sqlite3.Connection,
    paths: list[Path],
    project_root: Path,
    synced_by: str,  # 'watcher' | 'sync_cmd'
) -> dict[str, int]:
    """单事务重建整批文件。本模块对外的唯一入口。

    功能（只做调度，不做解析）：
      1. 用 ``with conn:`` 打开 **一个** 事务，把 ``paths`` 整批包进去。
      2. 对每个路径调用 ``_reindex_single_file``，它返回三种结果之一。
      3. 把三种结果累加成计数，交给 daemon / ``codeindex sync`` 打日志。

    为什么必须整批一个事务（design.md 2.4）：
      Agent 把 ``take_damage`` 从 a.gd 挪到 b.gd 会一次改两个文件。
      若每个文件单独 COMMIT，中间可能被 CLI 读到「两个文件都没有这个函数」。
      一个事务 = 读者要么看到挪之前，要么看到挪之后。

    ``with conn:`` 在 Python sqlite3 里的含义：
      进入时相当于 BEGIN；循环正常结束则 COMMIT；循环里抛出 **未捕获** 的异常则 ROLLBACK。
      parse 失败在 ``_reindex_single_file`` 里被吃掉并记 ``failed``，故意不往上抛，
      所以不会撑破这层事务——同批其它文件照样提交。只有 SQLite 自己炸了才会整批回滚。

    参数：
      conn         必须是 ``connection.connect_rw`` 拿到的写连接（只读 URI 会拒绝 INSERT）。
      paths        磁盘路径列表；绝对或相对都可以，入库前会收成相对 ``project_root``。
      project_root 被索引的游戏项目根（yaml 里的那个），不是 ``codebase_index/``。
      synced_by    只写进 ``files.last_synced_by``，方便调试是 watcher 还是 sync 写的；
                   不是检索键。合法值：``'watcher'`` | ``'sync_cmd'``。

    返回：
      ``{'reindexed': int, 'skipped': int, 'failed': int}``，三者之和等于 ``len(paths)``。
    """
    stats = {"reindexed": 0, "skipped": 0, "failed": 0}
    with conn:
        # SCENE_INDEX_TODO(step3-writer): 见 codebase_index/NEXT_STEP.md 第 7 节开头的「标记」说明。
        # 实现时在这个事务里按后缀分叉：.tscn / .tres 走 scene.store，不进 tree-sitter，不进 files。
        for path in paths:
            outcome = _reindex_single_file(conn, path, project_root, synced_by)
            stats[outcome] += 1
    return stats


def _reindex_single_file(
    conn: sqlite3.Connection,
    path: Path,
    project_root: Path,
    synced_by: str,
) -> str:
    """重建 **一个** 文件的索引行，返回 ``'reindexed'`` | ``'skipped'`` | ``'failed'``。

    功能：按下面五条分支决定「动不动库、怎么动」。
    调用方（``reindex_batch``）已经在事务里，本函数不要自己 ``commit`` / ``rollback``。

    返回值给上层计数用，不是写进某张表的列：
      reindexed  库被改了（新文件 / 内容变了 / 磁盘上删了）
      skipped    库没动（扩展名不认识，或 hash 与库中一致）
      failed     ``files`` 户口还在，但 parse 抛错，三张子表为空

    ------------------------------------------------------------------
    分支 1  没有 parser（.md / .tscn / .import …）
            本索引只管 .gd/.cs/.cpp/.h/.hpp。不写库，直接 skipped。
    分支 2  磁盘上没了（人类删文件、git checkout 掉了）
            ``DELETE FROM files WHERE path=?``。
            schema 里 ``ON DELETE CASCADE`` 会顺带清掉该 file_id 的
            symbols / edges / classes，避免孤儿行。仍记 reindexed：
            「库和磁盘对齐了」也是一次有效更新。
    分支 3  hash 与库中一致
            sync 刚写过、watcher 防抖稍后再命中同一文件，走这里。
            不跑 tree-sitter，不改任何行。
    分支 4  新文件，或旧文件内容变了
            upsert ``files``（更新 hash / language / last_synced_by / indexed_at），
            先按 file_id **手动** 删三张子表（UPDATE 不会触发 CASCADE，
            CASCADE 只在 DELETE 父行时发生），再 parse，再 INSERT 子行。
    分支 5  ``parser.parse()`` 抛异常（语法坏了、tree-sitter 内部出错）
            ``files`` 行已经写好（hash 是坏文件的 hash），子表保持空 → failed。
            空符号表 = Layer 2 查不到这个文件里的名字，兜底交给 Layer 3 workspace/symbol。
            下次再扫到同一内容会走分支 3 skipped，不会每 500ms 重解析一次坏文件（**重要，先校验哈希，再解析文件**）；
            人把语法修好后 hash 变了，才会再进分支 4。
    ------------------------------------------------------------------
    路径拆成两种身份（调用方给的 path 不统一：watcher 绝对，测试/sync 可能相对）：

      rel       写进 files.path 的钥匙。相对 project_root、posix 分隔。
                库不能存绝对路径：UNIQUE 必须跨机器稳定，
                /Users/a/game/player.gd 和 /Users/b/game/player.gd 不能变成两行。
      abs_path  磁盘把手。exists()/read_text() 相对的是进程 cwd，不是 project_root。
                若只用 rel，daemon 从别的目录启动会去 {cwd}/scripts/player.gd 找文件，
                误判「磁盘上没了」然后 DELETE FROM files。
    ------------------------------------------------------------------
    """
    rel = _relpath(path, project_root)
    parser = registry.get_parser(path)

    # 分支 1：registry 按后缀查表，没有映射就不是本层该管的文件。
    if parser is None:
        return "skipped"

    # 已是绝对路径（watcher）直接用；相对路径则钉到 project_root，避免跟进程 cwd 走。
    abs_path = path if path.is_absolute() else project_root / path

    # 分支 2：exists() 看的是磁盘，不是库。库里可能还有上次留下的 files 行。conn.execute(sql, params) 的第二个参数必须是 序列（tuple / list）。SQLite 按 ? 的顺序从里面取值。
    if not abs_path.exists():
        conn.execute("DELETE FROM files WHERE path = ?", (rel,))
        return "reindexed"

    # 坑：不要 hashlib.sha256(abs_path.read_bytes())。hash 必须和 parse() 吃的是同一份文本。
    # read_text(..., errors='replace') 会把非法 UTF-8 换成 U+FFFD（�），磁盘原字节 ≠ parser 看到的 str。
    # 若 hash 磁盘、parse 替换后的文本：files.content_hash 对不上「真正解析的那份」，
    # 分支 3 短路失效——坏字节文件每次 flush 都重跑 tree-sitter；或反过来 skip 了但库里记的不是解析输入。
    # 所以先 decode 成 source（后面 parse(rel, source) 就用它），再对这份 str encode 回 UTF-8 算 sha256。
    source = abs_path.read_text(encoding="utf-8", errors="replace")
    content_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    language = registry.language_of(path)

    row = conn.execute(
        "SELECT id, content_hash FROM files WHERE path = ?", (rel,)
    ).fetchone()

    # 分支 3：files.content_hash 列就是给这条短路用的。path UNIQUE，最多一行。
    if row is not None and row[1] == content_hash:
        return "skipped"

    now = time.time()
    if row is not None:
        file_id = int(row[0])
        # 内容变了：户口留下（id 不变，避免无意义地换主键），只刷新元数据和子表。
        conn.execute(
            "UPDATE files SET content_hash=?, language=?, last_synced_by=?, indexed_at=? WHERE id=?",
            (content_hash, language, synced_by, now, file_id),
        )
        # 这里已经过了分支 3：hash 变了，不是「只改一个符号就只补那一行」。
        # 粒度是整文件：先把该 file_id 的旧子行清空，下面 parse + _insert_parse_result 再整份插入。
        # 不按符号 diff 的原因：改一个名字也会让后面所有行号、edges.from/to、class 一起动；
        # 单文件 tree-sitter + 几十行 INSERT 很便宜，行级补丁更容易漏边、留下过期 line。
        # UPDATE 父行不会 CASCADE。必须按 file_id 自己清，否则旧 take_damage 会和新符号叠在一起。
        conn.execute("DELETE FROM symbols WHERE file_id=?", (file_id,))
        conn.execute("DELETE FROM edges WHERE file_id=?", (file_id,))
        conn.execute("DELETE FROM classes WHERE file_id=?", (file_id,))
    else:
        cur = conn.execute(
            "INSERT INTO files (path, content_hash, language, last_synced_by, indexed_at) VALUES (?,?,?,?,?)",
            (rel, content_hash, language, synced_by, now),
        )
        # lastrowid = 刚插入那一行的 INTEGER PRIMARY KEY（也就是后面子表的 file_id）。
        raw_id = cur.lastrowid
        if raw_id is None:
            raise RuntimeError("INSERT INTO files did not return lastrowid")
        file_id = int(raw_id)

    # 分支 4 / 5：户口已经对齐磁盘；能不能填子表取决于 parse。
    try:
        parsed = parser.parse(rel, source)
    except Exception:
        return "failed"

    _insert_parse_result(conn, file_id, parsed)
    return "reindexed"


def _relpath(path: Path, project_root: Path) -> str:
    """把磁盘路径收成 ``files.path`` 用的相对路径字符串。

    功能：daemon 的 watcher 给的是绝对路径；测试和 ``codeindex sync`` 可能给相对路径。
    库里必须统一成「相对 project_root、posix 分隔（/）」：
      - 相对：同一个 player.gd 在 macOS 与 Windows 上 path 字符串一致，UNIQUE 才对得上。
      - posix：Windows 的 ``scripts\\player.gd`` 不会和 ``scripts/player.gd`` 变成两行。

    实现：先 resolve 成绝对路径，再 ``relative_to(project_root)``。
    若 path 根本不在 project_root 下面（误传了别的盘符），relative_to 会抛 ValueError，
    退回绝对 posix 字符串，至少还能落库，不让整批事务炸掉。
    """
    resolved_root = project_root.resolve()
    resolved = path.resolve() if path.is_absolute() else (resolved_root / path).resolve()
    try:
        return resolved.relative_to(resolved_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _insert_parse_result(
    conn: sqlite3.Connection,
    file_id: int,
    parsed: ParseResult,
) -> None:
    """把一份已经解析好的 ``ParseResult`` 写成三张子表的行。

    功能：这里 **不再** 跑 tree-sitter、不读磁盘。只做 INSERT。
    调用时机：``_reindex_single_file`` 已经 upsert 过 ``files``、清空过该 file_id 的旧子行。

    三张表对应 parser 三个字段（和 gdscript.py 文件头那张对照表一致）：
      parsed.symbols[i]  → symbols   find-symbol 按 name 查
      parsed.edges[i]    → edges     call-chain 按 to_name 往上爬
      parsed.class_decl  → classes   class-hierarchy 按 name / base_name 爬
                           可为 None（文件里没有 class_name / class 声明）

    ``to_name`` / ``base_name`` 已经是 parser 从 CST 切出的源码原文，
    本函数原样写入，不做「绑到 symbols.id」——引擎 API（queue_free、CharacterBody2D）
    在本仓库里往往没有定义行，边仍然合法（schema 注释 / design.md 2.7）。

    ``executemany``：一次把列表里所有符号/边打进 SQLite，比 for 循环逐条 INSERT 少往返。
    空列表是合法的（解析成功但文件里没有函数）——executemany 对空序列什么都不做。
    """
    conn.executemany(
        "INSERT INTO symbols (file_id, name, kind, line, end_line, class_name, signature) VALUES (?,?,?,?,?,?,?)",
        [
            (file_id, s.name, s.kind, s.line, s.end_line, s.class_name, s.signature)
            for s in parsed.symbols
        ],
    )
    conn.executemany(
        "INSERT INTO edges (file_id, from_symbol, to_name, line, kind) VALUES (?,?,?,?,?)",
        [(file_id, e.from_symbol, e.to_name, e.line, e.kind) for e in parsed.edges],
    )
    if parsed.class_decl is not None:
        c = parsed.class_decl
        conn.execute(
            "INSERT INTO classes (file_id, name, base_name, line) VALUES (?,?,?,?)",
            (file_id, c.name, c.base_name, c.line),
        )
