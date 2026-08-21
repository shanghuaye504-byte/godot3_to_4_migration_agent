"""Kernel 层共享数据结构。

只含 dataclass / Enum，不含逻辑。RawResult 是 Kernel 唯一产出，也是
Analyzer 唯一输入 —— Analyzer 之后落地时不需要认识 Kernel 内部任何其他类型。
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
    """README §0.1 四元组：Measurement = (project, command, cache_state, repeat_idx)。"""

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
