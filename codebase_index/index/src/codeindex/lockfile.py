from __future__ import annotations

import fcntl
import os
import sys
from pathlib import Path


def acquire_singleton_lock(lock_path: Path) -> int:
    """
    抢独占非阻塞锁，成功返回 fd（须持有到进程退出，锁随 fd 关闭自动释放）。

    实现要点（design.md 2.2）：os.open(O_CREAT|O_RDWR) → fcntl.flock(LOCK_EX|LOCK_NB)，
    抢锁成功后 ftruncate 并写入自身 pid（CLI status/down 靠这个 pid 探活与发信号）。
    已有 daemon 在跑时打印 "daemon already running" 并以退出码 1 退出。
    """
    
    # ========== 第1步：确保锁文件的父目录存在 ==========
    # 锁文件路径类似：/project/.codeindex/daemon.lock
    # 第一次启动 daemon 时，.codeindex 目录可能还不存在，需要创建
    # parents=True：自动创建所有缺失的父目录
    # exist_ok=True：如果目录已存在也不报错
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    
    # ========== 第2步：打开（或创建）锁文件 ==========
    # os.open() 是底层系统调用，返回一个整数文件描述符（fd）
    # O_CREAT：如果文件不存在就创建一个空文件（注意：创建文件 ≠ 拿到锁）
    # O_RDWR：以读写模式打开，因为后面既要加锁（flock），又要写入 pid
    # 注意：这里用的是 os.open()，不是 Python 的 open()，因为我们需要整数 fd
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    
    # ========== 第3步：尝试抢锁（原子操作） ==========
    # fcntl.flock() 是系统调用，对文件描述符 fd 关联的文件加锁
    # LOCK_EX：独占锁（Exclusive），同一时间只能有一个进程持有
    # LOCK_NB：非阻塞（Non-Blocking），抢不到立刻抛异常，不等待
    # 两个标志用 |（按位或）组合：LOCK_EX | LOCK_NB
    # 效果：要么立刻抢到锁，要么立刻报错退出
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # ========== 第4步：抢锁失败 ==========
        # BlockingIOError 表示锁已被其他进程持有（已经有 daemon 在跑了）
        # 此时需要做两件事：
        # 1. 关闭自己打开的 fd（虽然没抢到锁，但文件已经打开了，不关会泄漏）
        # 2. 打印提示信息并退出（退出码 1 表示异常退出）
        os.close(fd)
        print("daemon already running, exiting", file=sys.stderr)
        sys.exit(1)
    
    # ========== 第5步：抢锁成功，写入 PID ==========
    # 能执行到这里，说明当前进程是唯一持有这把锁的 daemon
    # 注意：锁绑定在 fd 上，只要 fd 不关闭，锁就一直持有
    
    # ftruncate(fd, 0)：将文件大小截断为 0（清空文件内容）
    # 这是为了防止之前崩溃的 daemon 留下的旧 PID 信息干扰
    # 注意：ftruncate 只清空内容，不影响锁状态
    os.ftruncate(fd, 0)
    
    # 将当前进程的 PID 写入锁文件。这几位数字不是锁。
    # os.getpid() 返回当前进程的 PID（整数）
    # str().encode() 转成 bytes（os.write 不接受 str）
    #
    # 真正挡住第二个 daemon 的是上面的 flock；文件里的 pid 只给外面的 CLI 看：
    #   codeindex status → 读出整数后 os.kill(pid, 0) 探活（信号 0 不杀进程）
    #   codeindex down   → 对这个 pid 发 SIGTERM，让 daemon 走 finally 关库、关 fd
    # 没有这几位数字，status/down 就不知道该探谁、该杀谁。
    os.write(fd, str(os.getpid()).encode())
    
    # ========== 第6步：返回文件描述符 ==========
    # 返回的 fd 必须由调用方（daemon 主进程）一直持有，直到进程退出
    # 绝对不能在这里 close(fd)，否则锁会立即释放！
    # 当进程退出（正常退出或被 kill -9）时，内核会自动关闭所有 fd，锁自动释放
    return fd


"""
==================== 关键概念补充（注释里没写但很重要） ====================

1. flock 锁绑定在 fd 上，不是绑定在文件名上
   - 所以即使锁文件被删除，只要 fd 还在，锁依然有效
   - 进程退出时内核关闭 fd，锁自动释放（即使被 kill -9 也一样）

2. 为什么是 LOCK_EX | LOCK_NB？
   - LOCK_EX：独占锁，保证只有一个 daemon 能写
   - LOCK_NB：非阻塞，第二个 daemon 抢不到就立刻退出，不傻等
   - 两个标志用 | 组合成一个 bitmask 传给系统调用

3. 这和 threading.Lock 的区别：
   - threading.Lock：同一个进程内，多个线程之间互斥
   - flock：多个进程之间互斥（这里是防止两个 codeindexd 进程同时写）

4. 文件里的 PID 不是锁（flock vs pid 分工）
   - flock：保证全机只有一个 writer；没有它，两个 daemon 能同时写库
   - 文件里的 pid：告诉 CLI 该探谁、该杀谁；没有它，status/down 找不到目标进程
   - status：os.kill(pid, 0) —— 不杀进程，只探活。还在就 running，ESRCH 就当没在跑
   - down：对这个 pid 发 SIGTERM
   - 不能单凭「daemon.lock 里有个数字」判定 daemon 还在跑

5. 如果进程被 kill -9 会怎样？
   - 内核强制回收进程的所有资源，包括所有打开的文件描述符
   - 关闭 fd 时，flock 锁自动释放（os.close(lock_fd) 也是同一效果）
   - pid 会过期：锁已经没了，文件里可能还躺着旧数字
   - 下一个 daemon 抢到锁会先 ftruncate 再写自己的 pid
   - CLI 探活时若 kill(pid, 0) 失败（ESRCH），就当 daemon 已经不在
"""