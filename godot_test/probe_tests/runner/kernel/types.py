"""Kernel 的「场记单」：只有数据结构，没有执行逻辑。

两张最重要的表：

1. Measurement — 科学身份（README §0.1 四元组）
   「这条观测是：哪个项目 × 哪条指令 × 冷/热缓存 × 第几次重复」
   不含 run-id / N / step_id：那些是存档和编排用的，不是测量维度。

2. RawResult — 一次快门的全部底片
   Measurement 标签 + 实际 argv + stdout/stderr + 进程状态
   + 跑前/跑后文件快照 + git diff + 本步用过的 hook + inputs_digest。
   Kernel 的唯一产出，也是 Analyzer 的唯一输入。

其余类型都是 RawResult 的栏目：
  EngineProfile  用哪台 Godot（或 Fake）
  ProcessStatus  pid / rc / signal / timeout / 墙钟
  FsSnapshot     某一时刻工作区里每个文件的 sha1

本文件不 import process/workspace；谁填写这些格子由 runner + capture 决定。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CacheState(str, Enum):
    COLD = "COLD"
    WARM = "WARM"
    PRESERVE = "PRESERVE"


@dataclass(frozen=True)
class Measurement:
    """一次观测的科学坐标，不是磁盘路径。

    project      = group.fixture（如 phase1/CleanControl）
    command      = YAML 的 V1/V3/V9
    cache_state  = COLD / WARM / PRESERVE
    repeat_idx   = 同一 step 内的第几次（0-based）
    """

    project: str
    command: str
    cache_state: CacheState
    repeat_idx: int


@dataclass(frozen=True)
class EngineProfile:
    executable: tuple[str, ...]
    version: str
    build_hash: str
    fake: bool = False


@dataclass(frozen=True)
class FsEntry:
    rel_path: str
    size: int
    mtime_ns: int
    sha1: str
    is_dir: bool


@dataclass(frozen=True)
class FsSnapshot:
    taken_at: str
    entries: tuple[FsEntry, ...]


@dataclass(frozen=True)
class ProcessStatus:
    pid: int
    pgid: int
    returncode: Optional[int]
    signal: Optional[int]
    timed_out: bool
    wall_time_seconds: float
    started_at: str
    ended_at: str


@dataclass
class RawResult:
    """capture.run_measurement 的返回值：一条测量的完整原始记录。

    measurement     四元组标签（Measurement）
    step_id         编排名，便于对 YAML / 报告（如 v3-cold）
    argv            真正交给进程的参数列表
    process         rc / signal / timeout（ProcessStatus）
    fs_before/after 跑命令前后的文件树
    workspace_diff  相对 git 基线的 diff（不是 fs_before 与 fs_after 的差）
    inputs_digest   开拍前盖的输入指纹（digest.py 算，capture 只原样带上）
    """

    measurement: Measurement
    step_id: str
    argv: list
    cwd: str
    env_overrides: dict
    stdout: str
    stderr: str
    process: ProcessStatus
    fs_before: FsSnapshot
    fs_after: FsSnapshot
    workspace_diff: str
    hooks_applied: list = field(default_factory=list)
    inputs_digest: str = ""
