"""codeindexd —— 常驻 daemon，全系统唯一写者（design.md 2.1 / 2.2）。

启动顺序（严格）：
  1. acquire_singleton_lock —— 抢不到说明已有 daemon 在跑，直接退出（防并发拉起两个写者）
  2. 全量扫描 project_root，单事务落库
  3. 写 .codeindex/ready 时间戳 —— `codeindex up` 轮询这个文件出现才返回（消除冷启动竞态）
  4. 起文件监听 + DebouncedIndexer，常驻直到收到 SIGTERM/SIGINT

崩溃安全性：SQLite WAL 文件自洽，daemon 崩溃不损坏已 commit 的数据；
CI 场景可不做 down，让容器销毁顺带杀进程。

本模块第一次把「写路径」做成进程。查询由 `cli.py` 走只读连接。
"""

from __future__ import annotations

import os
import signal
import sqlite3
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

from watchfiles import Change, watch

from .config import load_config
from .db import connection, writer
from .lockfile import acquire_singleton_lock
from .parsers import registry
from .watcher import DebouncedIndexer

# os.walk 时从 dirnames 里抠掉这些名字，watch 时路径里出现同样也不索引。
# .codeindex 必须排除：daemon 自己写 index.db 会触发 FS 事件，否则会自我唤醒。
_SKIP_DIR_NAMES = frozenset({".godot", ".import", ".git", "__pycache__", ".codeindex"})


def _should_index(path: Path) -> bool:
    """这个路径要不要交给 writer。

    功能：两道门都过才算数。
      1. 路径上任何一段不能是 .godot / .git 等（导入缓存、版本库、本索引自己的状态目录）
      2. 扩展名必须在 parsers.registry 里（.gd / .cs / .cpp / .h / .hpp）
    不读文件内容、不跑 tree-sitter。删文件时磁盘上已经没了，仍然用后缀判断，
    好让 writer 走「文件不存在 → DELETE files」那一分支。
    """
    if any(part in _SKIP_DIR_NAMES for part in path.parts):
        return False
    # SCENE_INDEX_TODO(step3-scan): 见 codebase_index/NEXT_STEP.md 第 7 节开头的「标记」说明。
    # 实现时让 .tscn / .tres 也返回 True。_watch_filter 复用本函数，不必改 watcher.py。
    # 不要把这两种后缀塞进 tree-sitter registry。
    return registry.get_parser(path) is not None


def _iter_source_files(root: Path) -> Iterator[Path]:
    """遍历 project_root 下所有受支持的源码文件。

    功能：首次全量扫描的文件清单。用 os.walk 而不是 rglob，是为了能改 dirnames：
    把 .godot 从「待进入的子目录」里删掉，里面的文件根本不会被看到（比走完再过滤便宜）。

    排除 .godot/ .import/ .git/ __pycache__/ .codeindex/ ；扩展名交给 parsers.registry。
    """
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        #原地切片，用来给下一次递归进入子文件夹进行提前裁剪
        dirnames[:] = [name for name in dirnames if name not in _SKIP_DIR_NAMES]
        for filename in filenames:
            path = Path(dirpath) / filename
            if _should_index(path):
                yield path


def _full_scan(conn: sqlite3.Connection, project_root: Path) -> None:
    """首次全量扫描：收集全部源码文件，交给 writer.reindex_batch 单事务落库。

    功能：启动时把磁盘现状一次性对齐到 SQLite。synced_by 写成 watcher，
    因为这是 daemon 自己扫的，不是 CLI sync。空项目也合法：paths=[]，库里零行。
    """
    paths = list(_iter_source_files(project_root))
    stats = writer.reindex_batch(conn, paths, project_root, synced_by="watcher")
    print(
        f"full scan: {len(paths)} files, "
        f"reindexed={stats['reindexed']} skipped={stats['skipped']} failed={stats['failed']}",
        file=sys.stderr,
        flush=True,
    )


def _watch_filter(change: Change, path: str) -> bool:
    """watchfiles 每看到一个变化就会问：要不要把这件事交给 Python？

    功能：只放行「我们会索引的源码路径」。change 是 added/modified/deleted，
    三种都要（删文件也得通知 writer）。path 是字符串，先收成 Path 再复用 _should_index。
    """
    return _should_index(Path(path))


def main() -> None:
    """daemon 入口（pyproject 里注册为 codeindexd 命令）。

    关键步骤见模块 docstring 的启动顺序；watch 循环中每个受支持的文件变化
    都喂给 DebouncedIndexer；收到 SIGTERM/SIGINT 后 flush 残余 pending、commit、
    删 ready 标记、关闭连接再退出。

    本函数尽量用 try/finally：无论 Ctrl+C、SIGTERM，还是扫描中途炸了，
    都要摘掉 ready（避免 CLI 以为还活着）、关掉写连接。
    """
    # ----- 读配置（还不写任何运行时文件）-----
    try:
        cfg = load_config()
    except FileNotFoundError:
        print(
            "config.yaml not found; copy config.example.yaml to config.yaml",
            file=sys.stderr,
        )
        sys.exit(2)
    except Exception as exc:
        print(f"failed to load config: {exc}", file=sys.stderr)
        sys.exit(2)

    # ----- 第 1 步：抢单例锁。失败时 lockfile 自己 sys.exit(1) -----
    # 返回的 fd 必须赋给变量一直活到进程结束；不要 close。
    lock_fd = acquire_singleton_lock(cfg.lock_path)
    '''main 用 try/finally：不管后面成功还是 Ctrl+C、扫描中途报错，finally 里都要：

    有 indexer → flush_now()
    有 conn → close()
    但这两样 不是一开始就有的。可能在 connect_rw 之前就炸了（磁盘满、路径不对），那时还没有连接；也可能全量扫描失败，DebouncedIndexer 还没建出来。'''
    conn: sqlite3.Connection | None = None
    indexer: DebouncedIndexer | None = None
    try:
        # 旧 daemon 崩溃可能留下 ready。先删，避免 CLI 在本次扫描完成前误以为已经就绪。
        if cfg.ready_path.exists():
            cfg.ready_path.unlink()

        # ----- 第 2 步：打开写连接 + 全量扫描 -----
        conn = connection.connect_rw(cfg.db_path)
        print(f"scanning {cfg.project_root}", file=sys.stderr, flush=True)
        _full_scan(conn, cfg.project_root)

        # ----- 第 3 步：写 ready。codeindex up 轮询到这个文件才返回 -----
        cfg.ready_path.write_text(str(time.time()), encoding="utf-8")
        print(f"ready {cfg.ready_path}", file=sys.stderr, flush=True)

        # 闭包必须抓住「已经打开的写连接」，不能用可能为 None 的外层 conn 标注。
        rw_conn = conn

        def _reindex(paths: list[Path]) -> None:
            stats = writer.reindex_batch(
                rw_conn, paths, cfg.project_root, synced_by="watcher"
            )
            print(
                f"incremental: {len(paths)} files, "
                f"reindexed={stats['reindexed']} skipped={stats['skipped']} failed={stats['failed']}",
                file=sys.stderr,
                flush=True,
            )

        indexer = DebouncedIndexer(_reindex)

        # ============================================================
        # 关停 + 监听：signal / stop_event / watch / 两层 debounce
        # ============================================================
        #
        # 【signal 是什么】
        #   操作系统发给进程的一个整数通知。和函数返回值无关，随时可能插进来。
        #   SIGINT  = 2  终端按 Ctrl+C
        #   SIGTERM = 15  kill <pid>，以后 codeindex down 也发这个
        #   signal.signal(信号编号, 处理函数) 的意思：以后再来这个信号，别用默认行为
        #   （SIGINT 默认是立刻杀进程），改成调用我们写的函数。
        #
        # 【处理函数的两个参数（Python 规定的，不是我们发明的）】
        #   _request_stop(signum, frame)
        #     signum  刚才是哪一种信号（2 或 15）。我们两种都当「请停下来」，所以不用它。
        #     frame   被打断时主线程执行到哪一帧（调试用）。我们也不用。
        #   下划线前缀 = 接收了但故意忽略。
        #
        # 【为什么不能在处理函数里直接 close / flush】
        #   信号处理函数运行在「打断点」，里面做复杂的 SQLite / join 容易和主线程打架。
        #   约定：处理函数里只干一件极小的事——把一面旗子立起来。
        #
        # 【stop_event 是什么】
        #   threading.Event() = 进程里的一面旗，只有两种状态：没立（False）/ 立了（True）。
        #     .set()   立旗
        #     .is_set() 查旗
        #   watch() 会 **阻塞** 在「等内核的文件变化」上，主线程卡在 for 循环里，
        #   信号处理函数没有办法「return 一下让 for 结束」。
        #   所以把这面旗传给 watch(..., stop_event=stop_event)：
        #   库在内部每隔一小段时间看一眼旗，发现被 set 就结束生成器，for 循环自然退出，
        #   然后走到下面的 finally 去做 flush / 删 ready / 关连接。
        #
        # 【_request_stop 是什么】
        #   就是上面说的那面旗的 setter。SIGINT 和 SIGTERM 都注册成它。
        #   按一次 Ctrl+C → 内核发 SIGINT → Python 调 _request_stop → stop_event.set()
        #   → watch() 下一次醒来发现旗立了 → for 结束 → finally。
        #
        stop_event = threading.Event()

        def _request_stop(_signum: int, _frame: object) -> None:
            """只立旗，不关库、不 flush。真正的清理在 main 的 finally。"""
            stop_event.set()

        signal.signal(signal.SIGTERM, _request_stop)
        signal.signal(signal.SIGINT, _request_stop)

        # ----- 第 4 步：阻塞监听 -----
        #
        # watch() 是一个生成器：没有文件变化时线程睡在内核通知上；有变化就 yield 一批。
        # 每一批 changes 是一组 (Change, 路径字符串)，Change 是 added / modified / deleted。
        #
        # 参数：
        #   cfg.project_root   监听哪棵目录树（被索引的游戏项目，不是本仓库）
        #   watch_filter       每个变化先问一遍：要不要交给 Python。False 则丢掉。
        #                      我们用 _watch_filter：只要 .gd/.cs/.cpp，并跳过 .godot/.codeindex
        #   stop_event         上面那面旗；被 set 后 watch() 停止 yield
        #   debounce=1         **watchfiles 自己的** 合并窗口，单位毫秒，和 DebouncedIndexer 不是同一个东西
        #
        # 【两层 debounce，会不会冲突】
        #   层 A：watchfiles.watch(debounce=…)
        #         内核可能对一次保存连打好几条「改了」事件。这一层在 **进入 Python 之前**
        #         把很近的事件收成一批再 yield。它的默认值大约 1600ms。
        #   层 B：DebouncedIndexer（昨天写的，静默期 500ms，硬上限 2000ms）
        #         事件 **已经进到 Python** 之后，on_file_changed 才开始计时，决定何时 reindex_batch。
        #
        #   若层 A 用默认 1600ms：文件保存后要等约 1.6 秒 Python 才第一次接到路径，
        #   层 B 的 500ms 静默期几乎用不上（你感觉到的延迟已经被层 A 吃掉了）。
        #   两层都会「等」，但时钟起点不同，数字会叠加上去，表现为「改了文件要等两秒多才入库」。
        #
        #   所以层 A 设成 debounce=1（1 毫秒，几乎立刻把事件交给 Python），
        #   「等 500ms 再写库 / 最多 2000ms 必须写」全部交给层 B。两层不再抢语义。
        #   不是删掉层 B，也不是两套 500ms 各等一次。
        #
        print(f"watching {cfg.project_root}", file=sys.stderr, flush=True)
        for changes in watch(
            cfg.project_root,
            watch_filter=_watch_filter,
            debounce=1,
            stop_event=stop_event,
        ):
            for _change, path_str in changes:
                indexer.on_file_changed(Path(path_str))
    finally:
        # 关停顺序：先把防抖桶里还没写的刷掉 → 摘 ready → 关库。
        # 先摘 ready 再 flush 的话，CLI 会以为 daemon 已死，其实还在写最后一批。
        if indexer is not None:
            indexer.flush_now()
        if cfg.ready_path.exists():
            cfg.ready_path.unlink()
            print("removed ready", file=sys.stderr, flush=True)
        if conn is not None:
            conn.close()
        os.close(lock_fd)


if __name__ == "__main__":
    main()
