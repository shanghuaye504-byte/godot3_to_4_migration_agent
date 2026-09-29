"""第 10 步：编辑后对受影响文件跑 `codeindex sync`。

行为依据 NEXT_STEP.md「复用」与「Step 9」：用安装后的 `codeindex` 命令
（根环境的 path 依赖），参数是该文件的路径；失败不 reset，返回
`index_stale=true`。不在本目录重写 `reindex_batch`。
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def sync_file(project_root: str | Path, file: str, *, timeout: int = 120) -> bool:
    """对一个文件跑 `codeindex sync <path>`。成功返回 True，失败返回 False。

    `file` 是 res:// 形式；交给 codeindex 前转成绝对路径（cmd_sync 接受
    绝对路径，会自己收成 posix 相对路径入库）。
    """
    root = Path(project_root)
    rel = file[len("res://"):] if file.startswith("res://") else file
    target = str(root / rel)
    try:
        result = subprocess.run(
            ["codeindex", "sync", target],
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return result.returncode == 0
