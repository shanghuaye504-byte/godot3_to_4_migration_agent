"""generate_sentinel：V1 项目级扫描的哨兵。

由 kernel 在 V1（及 V7_V1 / V8_V1）步骤开始时写入、结束后删除。
扫描 workspace 下除 __probe_* 外的全部 .gd，写入 res://__probe_sentinel.gd
把它们逐个 preload。该文件不常驻 fixture。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

SENTINEL_NAME = "__probe_sentinel.gd"


def _collect_gd_files(workspace: Path) -> list:
    return sorted(
        p.relative_to(workspace).as_posix()
        for p in Path(workspace).rglob("*.gd")
        if not p.name.startswith("__probe_")
    )


def _safe_ident(rel_path: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in rel_path)


def apply(workspace: Path, *, context: Optional[dict] = None, **_ignored) -> Optional[Callable[[], None]]:
    workspace = Path(workspace)
    gd_files = _collect_gd_files(workspace)

    lines = ["extends Node", ""]
    for rel_path in gd_files:
        lines.append(f'const _{_safe_ident(rel_path)} = preload("res://{rel_path}")')

    sentinel_path = workspace / SENTINEL_NAME
    sentinel_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def revert() -> None:
        if sentinel_path.exists():
            sentinel_path.unlink()

    return revert
