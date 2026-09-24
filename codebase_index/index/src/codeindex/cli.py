"""codeindex —— 无状态只读 CLI（design.md 2.6）。

每次被 Agent 通过 Bash 调用时启动、查询、打印 JSON、退出，不持有长期状态。
唯一例外是 `sync` 子命令：它是 Agent 编辑工具的同步钩子，允许拿写连接绕开防抖。

和 daemon 的分工（再读一遍就记住）：
  codeindexd / python -m codeindex.daemon
      常驻。持有 flock、写连接、文件监听。一辈子只该有一个。
  codeindex（本文件）
      瞬时。起来、干一件事、把 JSON 打到 stdout、退出。
      不监听文件，也不该跟 daemon 抢写锁（sync 除外：它故意短时间当写者）。

退出码约定（Agent 先看数字，再看 JSON）：
  0 = 成功
  1 = 查无结果（daemon 活着、SQL 也跑了，只是库里没有这个名字）
  2 = 还没准备好（没 config、daemon 没起来、库文件不在、status 判定过期）
      提示先 `codeindex up`，不要当成「符号不存在」
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .config import Config, load_config
from .db import connection, queries, writer

EXIT_OK = 0
EXIT_NO_RESULT = 1
EXIT_NOT_READY = 2

# status：files.indexed_at 距现在超过这个秒数，就在 JSON 里标 stale=true，并以退出码 2 返回。
# 1 小时是「人离开电脑很久 / CI job 挂着没人碰」的量级，不是 watcher 的 500ms。
_STALE_SECONDS = 3600

# codeindex up 轮询 .codeindex/ready 的最长等待。大项目首次 tree-sitter 全量扫描可能要几十秒。
_UP_TIMEOUT_SECONDS = 120

# 轮询间隔。太密浪费 CPU；太疏会让 Agent 多等一轮才看到 ready。
_POLL_INTERVAL_SECONDS = 0.1


def _emit(payload: Any, exit_code: int = EXIT_OK) -> int:
    """把 payload 写成一行 JSON 打到 stdout，返回退出码（不在这里 sys.exit）。

    功能：所有子命令的唯一出口。stdout 只给机器看；人话、日志走 stderr。
    ensure_ascii=False：符号名里的非 ASCII 原样输出，不转成 \\uXXXX。
    default=str：万一 queries 漏出 Path / 异常对象，至少还能序列化，不把 CLI 打成 Traceback。
    调用方拿到返回值后自己 sys.exit(...)，这样单测如果以后要调 cmd_* 不会被强制杀掉进程。
    """
    json.dump(payload, sys.stdout, ensure_ascii=False, default=str)
    sys.stdout.write("\n")
    sys.stdout.flush()
    return exit_code


def _read_lock_pid(config: Config) -> int | None:
    """读 daemon.lock 里那串数字。读不到或不是整数 → None。

    这不是锁。真正挡住第二个 daemon 的是 flock（见 lockfile.py）。
    这里只是把「该探谁、该杀谁」的进程号拿出来。
    文件不存在、是空的、kill -9 留下的乱字节，都当「没有可用 pid」。
    """
    path = config.lock_path
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _process_argv(pid: int) -> str | None:
    """把 ``pid`` 的命令行收成一行普通字符串。读不到返回 None。

    不绑定某一家操作系统，按运行时「哪条通道存在用哪条」：

      1. ``/proc/<pid>/cmdline`` —— Linux / WSL / 其它带 procfs 的系统。
         字节之间是 ``\\0``，换成空格后就是 argv。
      2. ``ps -p <pid> -o args=`` —— POSIX 上常见的后备（macOS、BSD、没有 procfs
         的 Linux 容器）。``args=`` 表示只要命令行、不要列名表头。
      3. Windows 没有上面两条时，问 Win32 进程的 CommandLine。

    三条都失败就返回 None，调用方按「认不出来」处理，不要猜。
    """
    procfs = Path("/proc") / str(pid) / "cmdline"
    try:
        raw = procfs.read_bytes()
    except OSError:
        raw = b""
    if raw:
        return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()

    try:
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "args="],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        completed = None
    if completed is not None and completed.returncode == 0:
        text = completed.stdout.strip()
        if text:
            return text

    if os.name == "nt":
        return _windows_command_line(pid)
    return None


def _windows_command_line(pid: int) -> str | None:
    """Windows：用 WMI 取进程命令行。本机没有 PowerShell/WMI 时返回 None。"""
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    text = completed.stdout.strip()
    return text or None


def _pid_alive(pid: int) -> bool:
    """这个 pid 现在是不是咱们的 daemon（还活着，且命令行对得上）。

    只做 kill(pid, 0) 不够：进程死掉后内核会把同一个号码发给别人。
    那时候 kill(0) 仍成功，但那已经不是 codeindexd。down 若据此 SIGTERM 会杀错进程。

    两道门都过才返回 True：
      1. 这个号码上现在有进程（kill 信号 0：不杀，只询问）
      2. 它的 argv 里能看到 ``codeindex.daemon`` 或 ``codeindexd``
         （``uv run python -m codeindex.daemon`` / 入口脚本 ``codeindexd``）
    读不到命令行也当 False：宁可不杀，也不要误杀。
    本函数没有 lock 路径，不能查 flock；「有没有人握着锁」是 ``_daemon_running`` 的事。
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # 进程存在但我们碰不到。没法核对 argv，不能当成 daemon。
        return False
    except OSError:
        return False

    args = _process_argv(pid)
    if not args:
        return False
    return "codeindex.daemon" in args or "codeindexd" in args


def _daemon_running(config: Config) -> bool:
    """daemon 现在还握着单例锁吗？试抢 flock，不看 pid 活不活。

    pid 文件会过期（kill -9 后数字还在，号码可能已经给了别人）。
    flock 绑在持有者的 fd 上：进程一死 fd 关掉，锁立刻没了。
    所以「还在跑」的权威信号是：这把 LOCK_EX 现在能不能被别人抢走。

      锁文件不存在 / 打开失败     → 从没人当过 daemon，False
      flock 抢到了                 → 没人握着。立刻 close(fd) 把刚抢到的锁放掉
                                     （不放的话 CLI 自己变成单例持有者，真 daemon 起不来）
      BlockingIOError              → 有人握着。那只能是 acquire_singleton_lock 的 codeindexd，True

    试抢不要 O_CREAT：只是打听，不该由 CLI 凭空造出 daemon.lock。
    """
    import fcntl

    path = config.lock_path
    if not path.exists():
        return False
    try:
        fd = os.open(path, os.O_RDWR)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return True
    except OSError:
        os.close(fd)
        return False
    # 抢到了 = 刚才没有持有者。close 会释放这次误抢的锁。
    os.close(fd)
    return False


def _require_ready(config: Config) -> None:
    """查询类命令的门卫：daemon 未跑或 index.db 不存在 → JSON 错误并以退出码 2 退出。

    功能：把「库还没建好」和「符号真的不存在」分开。
    前者是操作问题（先 codeindex up），退出码 2；后者才是退出码 1。
    不查 ready 文件本身：ready 在关停时会先被删，但 db 还在；查询认「进程活着 + 库文件在」。
    本函数成功时什么都不返回，失败时直接 sys.exit，不再回到 cmd_*。
    """
    running = _daemon_running(config)
    db_exists = config.db_path.exists()
    if running and db_exists:
        return
    payload = {
        "error": "daemon 未运行或索引库不存在，请先执行 codeindex up",
        "running": running,
        "db_exists": db_exists,
    }
    sys.exit(_emit(payload, EXIT_NOT_READY))


def cmd_up(config: Config, _args: argparse.Namespace) -> int:
    """启动 daemon。已经在跑就直接成功。

    流程：没有 → 后台拉起 → 等到 ``ready`` 文件出现再返回。
    必须等 ``ready``：那是首次扫描完成的标记。不等的话索引还是空的，
    后面查符号会得到空结果，Agent 会以为符号不存在。
    120 秒还没有 ``ready`` → 退出码 2。
    """
    if _daemon_running(config):
        return _emit(
            {
                "ok": True,
                "already_running": True,
                "pid": _read_lock_pid(config),
            }
        )

    # 没人握锁，但磁盘上可能还留着上一任崩溃时的旧 ready ——daemon 要等
    # 抢到锁之后才会删旧 ready、才开始扫描，进程启动那一小段时间里旧文件还在。
    # 不清掉的话，下面第一次循环检查就会把「上次扫完」误判成「这次扫完了」。
    # 刚确认过没人持锁，删它是安全的：不会有活着的 daemon 依赖这份文件。
    try:
        config.ready_path.unlink()
    except FileNotFoundError:
        pass

    # 后台启动，和当前 CLI 断开进程组：你 Ctrl+C 掉 up，daemon 还继续跑。
    proc = subprocess.Popen(
        [sys.executable, "-m", "codeindex.daemon"],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )

    deadline = time.monotonic() + _UP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        # daemon 扫完会写这个文件。看见它 = 可以查库了。
        if config.ready_path.exists():
            return _emit(
                {
                    "ok": True,
                    "already_running": False,
                    "pid": _read_lock_pid(config),
                }
            )
        # 我们拉起的那个进程已经退出。
        if proc.poll() is not None:
            if _daemon_running(config):
                # 别的 up 抢先拿到了锁，可能还在扫描、还没写 ready。
                # 这不是失败，继续等下一轮，不要提前汇报成功。
                time.sleep(_POLL_INTERVAL_SECONDS)
                continue
            if config.ready_path.exists():
                # 极小概率的时序缝隙：刚才两次检查之间它写完了 ready。
                return _emit(
                    {
                        "ok": True,
                        "already_running": True,
                        "pid": _read_lock_pid(config),
                    }
                )
            return _emit(
                {
                    "ok": False,
                    "error": "daemon 在写出 ready 之前就退出了（看终端 stderr：缺 config / 抢锁失败 / 扫描出错）",
                    "exit_code": proc.returncode,
                },
                EXIT_NOT_READY,
            )
        time.sleep(_POLL_INTERVAL_SECONDS)

    return _emit(
        {
            "ok": False,
            "error": f"等待 ready 超时（{_UP_TIMEOUT_SECONDS}s）。daemon 可能仍在扫大项目，可用 codeindex status 再看一眼",
            "pid": _read_lock_pid(config),
        },
        EXIT_NOT_READY,
    )


def cmd_status(config: Config, _args: argparse.Namespace) -> int:
    """查 daemon 是否存活、上次索引时间、是否过期（超过 _STALE_SECONDS 视为过期，退出码 2）。

    「活不活」用 _daemon_running（试抢 flock），不用 _pid_alive。
    pid 文件里的号码可能是上一任崩溃后的旧号码，被系统分配给一个恰好也叫
    codeindex.daemon 的无关进程时，_pid_alive 会认错；flock 绑在真正持有者
    的 fd 上，不会认错。pid 字段仍然读出来，只是给人看，不参与判断。
    """
    pid = _read_lock_pid(config)
    running = _daemon_running(config)
    if not running:
        return _emit(
            {
                "running": False,
                "pid": pid,
                "error": "daemon 未运行，请先执行 codeindex up",
            },
            EXIT_NOT_READY,
        )

    if not config.db_path.exists():
        return _emit(
            {
                "running": True,
                "pid": pid,
                "error": "daemon 在跑但 index.db 还不存在（扫描尚未写出？）",
            },
            EXIT_NOT_READY,
        )

    # 只读连接：status 不改库。daemon 同时在 WAL 里写也没关系（见 connection.py）。
    conn = connection.connect_ro(config.db_path)
    try:
        stats = queries.status(conn)
    finally:
        conn.close()

    last = stats["last_indexed_at"]
    # 空项目 MAX(indexed_at) 是 NULL：库是新的、只是没有文件，不算过期。
    stale = (
        last is not None and (time.time() - float(last)) > _STALE_SECONDS
    )
    payload = {
        "running": True,
        "pid": pid,
        "files": stats["files"],
        "symbols": stats["symbols"],
        "last_indexed_at": last,
        "stale": stale,
        "stale_after_seconds": _STALE_SECONDS,
    }
    return _emit(payload, EXIT_NOT_READY if stale else EXIT_OK)


def cmd_down(config: Config, _args: argparse.Namespace) -> int:
    """向 daemon 发 SIGTERM 优雅停止。

    SIGTERM（15）和 Ctrl+C 的 SIGINT 在 daemon 里注册的是同一个处理函数：
    只把 stop_event 这面旗立起来，watch() 循环结束后走 finally：
    flush_now → 删 ready → 关连接 → os.close(lock_fd) 放掉 flock。
    不要在这里 kill -9：那样跳过 finally，ready 可能残留（下次启动 daemon 会自己删）。
    已经没在跑则幂等返回 ok，避免脚本收尾时因为「本来就没起来」变成失败。

    「要不要发信号」用 _daemon_running（试抢 flock）判断，不用 _pid_alive：
    pid 文件里的号码可能过期，只信它就发 SIGTERM 有误杀无关进程的风险。
    确认真有人握着锁之后才读 pid 当目标；发送之后原地等它退出，这时候
    pid 已经核实过是谁，用 _pid_alive 探这一个具体号码没有问题。
    """
    if not _daemon_running(config):
        return _emit({"ok": True, "was_running": False, "pid": _read_lock_pid(config)})

    pid = _read_lock_pid(config)
    if pid is None:
        # 锁确实有人握着，但这一刻读不出 pid（读到锁文件被截断的极端时序）。
        # 没有号码没法发信号，如实报错，不要假装已经停了。
        return _emit(
            {
                "ok": False,
                "was_running": True,
                "pid": None,
                "error": "daemon 在跑但读不到 pid，无法发送 SIGTERM",
            },
            EXIT_NOT_READY,
        )

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        # 发信号前它自己已经退出（比如同时有人也在关它）。当作已经停了。
        return _emit({"ok": True, "was_running": True, "pid": pid, "still_alive": False})

    # 等一小会儿，好让 JSON 里的状态接近「已经停了」。不等满也不当失败：
    # finally 里还要 flush，大项目最后一批可能超过 2 秒。
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            break
        time.sleep(_POLL_INTERVAL_SECONDS)

    return _emit(
        {
            "ok": True,
            "was_running": True,
            "pid": pid,
            "still_alive": _pid_alive(pid),
        }
    )


def _open_ro(config: Config) -> sqlite3.Connection:
    """查询命令共用：门卫通过之后打开只读连接。调用方必须 close。"""
    _require_ready(config)
    return connection.connect_ro(config.db_path)


def cmd_find_symbol(config: Config, args: argparse.Namespace) -> int:
    """精确匹配符号名 → 定义位置列表（走只读连接）。"""
    # SCENE_INDEX_TODO(step3-find-symbol-exit): 见 codebase_index/NEXT_STEP.md 第 7 节开头的「标记」说明。
    # 实现时：没有代码符号但 scene_usages 非空，退出码用 0，不要用下面的 EXIT_NO_RESULT。
    conn = _open_ro(config)
    try:
        rows = queries.find_symbol(conn, args.name)
    finally:
        conn.close()
    if not rows:
        return _emit({"name": args.name, "matches": []}, EXIT_NO_RESULT)
    return _emit({"name": args.name, "matches": rows})


def cmd_call_chain(config: Config, args: argparse.Namespace) -> int:
    """调用者链，--depth 默认 3（走只读连接）。"""
    conn = _open_ro(config)
    try:
        rows = queries.call_chain(conn, args.name, depth=args.depth)
    finally:
        conn.close()
    if not rows:
        return _emit(
            {"name": args.name, "depth": args.depth, "callers": []},
            EXIT_NO_RESULT,
        )
    return _emit({"name": args.name, "depth": args.depth, "callers": rows})


def cmd_class_hierarchy(config: Config, args: argparse.Namespace) -> int:
    """祖先链 + 子类列表（走只读连接）。

    queries.class_hierarchy 查不到时仍返回 dict（ancestors/subclasses 都是 []），
    不会给 None。两边都空才算「这个名字在继承图里没出现过」→ 退出码 1。
    只问引擎类 CharacterBody2D 时，祖先可能为空、子类仍有，那是有效结果，退出码 0。
    """
    conn = _open_ro(config)
    try:
        result = queries.class_hierarchy(conn, args.name)
    finally:
        conn.close()
    if not result["ancestors"] and not result["subclasses"]:
        return _emit(result, EXIT_NO_RESULT)
    return _emit(result)


def cmd_sync(config: Config, args: argparse.Namespace) -> int:
    """Agent 编辑工具的同步钩子：绕开防抖，单事务立即重建指定文件。

    设计意图：Agent 写完文件的下一步往往就是查该文件的符号，不应等 watcher 的 500ms 静默期。
    最好由 Agent 框架的 write_file/str_replace 实现自动调用本命令（design.md 2.3 主动路径）。
    这是 CLI 唯一允许使用 connect_rw() 的子命令。
    """
    # 相对路径钉到 project_root，避免 CLI 的 cwd 和游戏项目根不是同一个目录。
    # 已经是绝对路径的（Agent 常给这个）原样交给 writer，它会收成 posix 相对路径入库。
    paths = [Path(p) for p in args.paths]
    conn = connection.connect_rw(config.db_path)
    try:
        stats = writer.reindex_batch(
            conn, paths, config.project_root, synced_by="sync_cmd"
        )
    finally:
        conn.close()
    return _emit(
        {
            "ok": True,
            "paths": [str(p) for p in paths],
            "reindexed": stats["reindexed"],
            "skipped": stats["skipped"],
            "failed": stats["failed"],
        }
    )


def build_parser() -> argparse.ArgumentParser:
    """构建子命令解析器。--help 文本即 Agent 的「命令手册」（design.md 2.8）。

    没有 MCP 的 inputSchema 时，Agent / 人都靠这一份 help 知道有哪些命令、参数叫什么。
    每个子命令的 help/description 写完整句，不要只写一个词。
    """
    parser = argparse.ArgumentParser(
        prog="codeindex",
        description=(
            "Godot 项目符号索引的无状态 CLI。"
            "查询走只读连接；先 codeindex up 拉起常驻 daemon，再查符号 / 调用链 / 继承。"
            "stdout 一律 JSON；退出码 0 成功、1 查无结果、2 未就绪（先 up）。"
        ),
    )
    # --json 挂在每个子命令上（parents=），这样 `codeindex find-symbol take_damage --json`
    # 能过 argparse。输出本来就是 JSON，这个旗只是和文档写法兼容，cmd_* 不读它。
    json_flag = argparse.ArgumentParser(add_help=False)
    json_flag.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON（默认就是 JSON，这个开关是为了和文档里的写法兼容）",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    # SCENE_INDEX_TODO(step5-scene-check): 见 codebase_index/NEXT_STEP.md 第 7 节开头的「标记」说明。
    # 实现时在这里注册 scene-check。跑完退出码 0，库没准备好退出码 2。不要用 1 表示有 regression。

    def _sub(name: str, **kwargs: Any) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[json_flag], **kwargs)

    # 生命周期 ----------------------------------------------------------
    p_up = _sub(
        "up",
        help="拉起 daemon，阻塞到首次扫描完成（ready 出现）",
        description=(
            "幂等启动 codeindexd。"
            "已经在跑则立刻返回；否则后台拉起 python -m codeindex.daemon，"
            "轮询 .codeindex/ready 最多 120 秒。必须等 ready，否则冷启动时索引还是空的。"
        ),
    )
    p_up.set_defaults(func=cmd_up)

    p_status = _sub(
        "status",
        help="看 daemon 是否存活、库有多大、索引是否过期",
        description=(
            "读 lock 文件里的 pid 探活，再用只读连接查 files/symbols 计数。"
            "上次索引距今超过 3600 秒则 stale=true、退出码 2。"
        ),
    )
    p_status.set_defaults(func=cmd_status)

    p_down = _sub(
        "down",
        help="向 daemon 发 SIGTERM，优雅停止",
        description=(
            "对 daemon.lock 里的 pid 发送 SIGTERM。"
            "daemon 会 flush 残余文件、删 ready、关库、释放 flock。"
            "本来就没在跑也返回成功。"
        ),
    )
    p_down.set_defaults(func=cmd_down)

    # 只读查询 ----------------------------------------------------------
    p_find = _sub(
        "find-symbol",
        help="精确匹配符号名，返回定义位置",
        description=(
            "SELECT 名字完全相等的 symbols 行（不是子串）。"
            "同名可有多处。一个都没有则退出码 1。"
        ),
    )
    p_find.add_argument("name", help="符号名，例如 take_damage")
    p_find.set_defaults(func=cmd_find_symbol)

    p_chain = _sub(
        "call-chain",
        help="谁调用了这个名字，再往上爬若干层",
        description=(
            "沿 edges 表 kind=call 反向爬调用者。"
            "--depth 默认 3；depth<1 会得到空列表。"
        ),
    )
    p_chain.add_argument("name", help="被调用的符号名，例如 _die")
    p_chain.add_argument(
        "--depth",
        type=int,
        default=3,
        help="最多爬几层（默认 3）",
    )
    p_chain.set_defaults(func=cmd_call_chain)

    p_hier = _sub(
        "class-hierarchy",
        help="类的祖先链 + 直接子类",
        description=(
            "祖先沿 classes.base_name 往上走；子类是 base_name 等于该类名的行。"
            "祖先和子类都空则退出码 1。"
        ),
    )
    p_hier.add_argument("name", help="类名，例如 Player")
    p_hier.set_defaults(func=cmd_class_hierarchy)

    # 唯一写路径 --------------------------------------------------------
    p_sync = _sub(
        "sync",
        help="立刻重建指定文件（绕开 watcher 的 500ms 防抖）",
        description=(
            "Agent 刚写完文件、马上要查符号时用。"
            "内部就是 writer.reindex_batch(..., synced_by='sync_cmd')，整批一个事务。"
            "这是 CLI 唯一会打开写连接的子命令。"
        ),
    )
    p_sync.add_argument(
        "paths",
        nargs="+",
        help="一个或多个源文件路径（相对项目根或绝对路径）",
    )
    p_sync.set_defaults(func=cmd_sync)

    return parser


def main() -> None:
    """CLI 入口（pyproject 里注册为 codeindex 命令）。

    顺序：解析参数 → 读 yaml → 按子命令 dispatch。
    load_config 失败（文件没有、字段缺）一律退出码 2，不要把 KeyError 堆栈甩给 Agent。
    没给子命令时打印 help，同样退出码 2（还没做任何查询）。
    """
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "func", None):
        parser.print_help()
        sys.exit(EXIT_NOT_READY)

    try:
        cfg = load_config()
    except FileNotFoundError:
        print(
            "config.yaml 不存在；请把 config.example.yaml 复制成 config.yaml 并填项目路径",
            file=sys.stderr,
        )
        sys.exit(EXIT_NOT_READY)
    except Exception as exc:
        print(f"读取 config.yaml 失败：{exc}", file=sys.stderr)
        sys.exit(EXIT_NOT_READY)

    sys.exit(args.func(cfg, args))


if __name__ == "__main__":
    main()
