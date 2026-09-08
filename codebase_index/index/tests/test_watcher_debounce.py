"""用 fake clock + fake timer 测防抖/硬上限时序，不依赖真实文件系统延迟。

覆盖要点：
- 静默期语义：500ms 内连续事件合并成一次 flush，timer 被重置
- 硬上限语义：事件每 400ms 来一个、静默期永远等不到时，2000ms 硬上限强制 flush，
  且 flush 携带全部 pending 文件（索引不被无限期推迟）

做法：monkeypatch threading.Timer 为手动触发的 FakeTimer，clock 注入可推进的 FakeClock。
本文件不 import writer / sqlite。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codeindex import watcher


class FakeClock:
    """测试用时钟。advance 立刻把「现在」往前拨，不 sleep。"""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeTimer:
    """不启动真实线程。start 只记账，测试里手动 fire。cancel 后 fire 是空操作。"""

    def __init__(self, interval, function, args=None, kwargs=None) -> None:
        self.interval = interval
        self.function = function
        self.args = args or ()
        self.kwargs = kwargs or {}
        self._cancelled = False
        self._started = False

    def start(self) -> None:
        self._started = True

    def cancel(self) -> None:
        self._cancelled = True

    def fire(self) -> None:
        if self._started and not self._cancelled:
            self.function(*self.args, **self.kwargs)


def _install_fake_timer(monkeypatch) -> list[FakeTimer]:
    """把 watcher.threading.Timer 换成 FakeTimer，并记下每一次构造。"""
    created: list[FakeTimer] = []

    def factory(interval, function, args=None, kwargs=None) -> FakeTimer:
        timer = FakeTimer(interval, function, args, kwargs)
        created.append(timer)
        return timer

    monkeypatch.setattr(watcher.threading, "Timer", factory)
    return created


def test_quiescence_merges_events_within_500ms_into_one_flush(monkeypatch) -> None:
    clock = FakeClock()
    flushes: list[set[Path]] = []
    timers = _install_fake_timer(monkeypatch)
    indexer = watcher.DebouncedIndexer(
        reindex_fn=lambda paths: flushes.append(set(paths)),
        clock=clock,
    )

    a, b, c = Path("a.gd"), Path("b.gd"), Path("c.gd")
    indexer.on_file_changed(a)
    assert timers[-1].interval == pytest.approx(0.5)

    clock.advance(0.2)
    indexer.on_file_changed(b)
    assert timers[-2]._cancelled
    assert timers[-1].interval == pytest.approx(0.5)

    clock.advance(0.2)
    indexer.on_file_changed(c)
    assert timers[-2]._cancelled
    assert timers[-1].interval == pytest.approx(0.5)

    timers[-1].fire()
    assert len(flushes) == 1
    assert flushes[0] == {a, b, c}


def test_max_wait_flushes_all_pending_when_events_never_go_quiet(monkeypatch) -> None:
    clock = FakeClock()
    flushes: list[set[Path]] = []
    timers = _install_fake_timer(monkeypatch)
    indexer = watcher.DebouncedIndexer(
        reindex_fn=lambda paths: flushes.append(set(paths)),
        clock=clock,
    )

    paths = [Path(f"f{i}.gd") for i in range(6)]
    for i, path in enumerate(paths):
        if i:
            clock.advance(0.4)
        indexer.on_file_changed(path)
        elapsed = i * 0.4
        delay = min(0.5, max(0.0, 2.0 - elapsed))
        assert timers[-1].interval == pytest.approx(delay)
        if i:
            assert timers[-2]._cancelled

    assert timers[-1].interval == pytest.approx(0.0)
    timers[-1].fire()
    assert len(flushes) == 1
    assert flushes[0] == set(paths)
