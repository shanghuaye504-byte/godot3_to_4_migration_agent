"""被动路径：文件变化监听 + 静默期防抖（design.md 2.3）。

防抖语义：连续 quiescence_ms 没有新事件才真正触发重建，把一串密集变化合并成一次；
同时有 max_wait_ms 硬上限，事件持续不断时强制 flush，防止索引被无限期推迟。
推荐参数：静默期 500ms，硬上限 2000ms。

注意：Agent 自己刚编辑的文件不走这条路（500ms 静默期对 Agent 工作流是不必要延迟），
那条走 CLI 的 `codeindex sync <path>` 同步钩子。本 watcher 只兜底"Agent 编辑工具之外
发生的变化"（人类协作、git pull、脚本生成代码）。两条路径互不冲突：
sync 命中的文件之后再被 watcher 事件命中时，writer 靠 content_hash 幂等跳过。

本模块不碰 SQLite、不读磁盘。它只决定「何时把一堆 Path 交给 reindex_fn」。
reindex_fn 在 daemon 里通常包一层 writer.reindex_batch。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

DEFAULT_QUIESCENCE_MS = 500
DEFAULT_MAX_WAIT_MS = 2000


class DebouncedIndexer:
    """静默期防抖索引器。reindex_fn 通常是 db.writer.reindex_batch 的薄包装。

    两个时钟：
      quiescence  距「上一次事件」再安静这么久才 flush（会被新事件重置）
      max_wait    距「本轮第一个事件」最多等这么久，到了必须 flush

    delay = min(quiescence, max(0, max_wait - 距首个 pending 的时长))
    事件很疏：每次都等到满静默期。
    事件很密（间隔 < 静默期）：静默期永远等不到，delay 被硬上限越削越短，直到 0。
    """

    def __init__(
        self,
        reindex_fn: Callable[[list[Path]], None],
        quiescence_ms: int = DEFAULT_QUIESCENCE_MS,
        max_wait_ms: int = DEFAULT_MAX_WAIT_MS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """clock 可注入 fake clock，测试防抖时序不依赖真实 sleep。

        功能：只存回调和两个阈值。pending / timer / 首事件时刻在第一次
        on_file_changed 时才有意义。threading.Lock 保护这三块共享状态：
        Timer 线程跑 _flush，watch 循环线程跑 on_file_changed。
        """
        self._reindex_fn = reindex_fn
        # Timer 的 interval 是秒；对外参数是毫秒，和 design.md 的 500 / 2000 对齐。
        self._quiescence = quiescence_ms / 1000.0
        self._max_wait = max_wait_ms / 1000.0
        self._clock = clock
        self._pending: set[Path] = set()
        self._timer: threading.Timer | None = None
        self._first_pending_at: float | None = None
        self._lock = threading.Lock()

    def on_file_changed(self, path: Path) -> None:
        """登记一个变化事件：加入 pending 集合并重置防抖计时器。

        功能：不重建索引。只记账 + 重新计算「还要再等多久才 flush」。

        时序规则：delay = min(quiescence, max(0, max_wait - 距首个 pending 事件的时长))。
          - 本轮第一个文件：first_pending_at 钉在现在，delay = quiescence（还没碰到硬上限）
          - 之后每个文件：取消旧 Timer，用同一把 first_pending_at 重算 delay
          - 距首事件已 ≥ max_wait：delay = 0，Timer 一启动就该立刻 _flush

        pending 用 set：同一文件 500ms 内保存两次只占一项，flush 仍是一次。
        """
        with self._lock:
            self._pending.add(path)
            if self._first_pending_at is None:
                self._first_pending_at = self._clock()
            if self._timer is not None:
                # 旧静默期作废。cancel 只对「还没开始跑回调」的 Timer 有效。
                self._timer.cancel()
                self._timer = None

            elapsed = self._clock() - self._first_pending_at
            delay = min(self._quiescence, max(0.0, self._max_wait - elapsed))
            # 通过 threading.Timer 查找，测试才能 monkeypatch 成 FakeTimer。
            self._timer = threading.Timer(delay, self._flush)
            self._timer.start()

    def _flush(self) -> None:
        """取出并清空 pending 集合，调用 reindex_fn 批量重建（内部应是单事务）。

        功能：本轮结束。清空 first_pending_at，下一轮事件会重新钉时间原点。
        reindex_fn 在锁外调用：避免重建（可能几百毫秒）挡住新的 on_file_changed，
        也避免回调里再拿锁死锁。pending 为空时不叫 reindex_fn（flush_now 的空转）。
        """
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            batch = list(self._pending)
            self._pending.clear()
            self._first_pending_at = None
        if batch:
            self._reindex_fn(batch)

    def flush_now(self) -> None:
        """不等静默期，立刻把当前 pending 刷出去。

        功能：给测试和 daemon 关停用。SIGTERM 时若不 flush，最后几百毫秒的改动会丢。
        内部就是 cancel + _flush。
        """
        self._flush()
