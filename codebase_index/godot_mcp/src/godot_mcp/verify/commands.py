"""VERIFY_COMMANDS 固定命令行白名单 —— 唯一允许新增校验命令的地方。

key 是探针实验锁定的内部命令 ID（V1 / V2 / V3），不是 MCP 工具的 kind。
Agent 只能选 `check_file` / `check_workspace`，由 `verify_gate.tool` 映射到这里。

生产子集（Godot 4.7.1.stable，探针 N01–N09 / N15）：
- V1  项目级 --check-only。必须带哨兵脚本；裸 --check-only 是 no-op。
      argv 固定指向 res://__probe_sentinel.gd；文件由 runner 写入/删除。
- V2  单文件 --check-only。消化 V1 抽出的 target_res_path。
- V3  --editor --import。shader / UID / class cache。本模块只提供 argv，
      外壳何时调度不在这里决定。

明确不进表（探针已否决或未作为生产主通道）：
- V4  不带 --editor 的 --import：N08 与 V3 行为一致，尚未被带真实资源的项目推翻
- V5  --quit：交叉验证信号源，不能当 reward（N08 B9）
- V6  --quit-after 2：不改变 rc / 防挂死语义
- V7  --verbose：无额外结构化信息
- V8  --debug：signal 11，永久禁入

注意：
1. `--script` 必须配合 `--path <project_root>`，否则 res:// 解析会错。
2. 单文件检查用 res://<相对路径>，不用绝对路径。
3. 本模块只负责 argv，不写哨兵、不起子进程。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

SENTINEL_RES_PATH = "res://__probe_sentinel.gd"


def _to_res_path(target: str, project_root: Path) -> str:
    """把 target 收成 Godot 能加载的 res:// 路径。"""
    if target.startswith("res://"):
        return target
    target_path = Path(target)
    if target_path.is_absolute():
        try:
            rel = target_path.relative_to(project_root.resolve())
        except ValueError as exc:
            raise ValueError(
                f"V2 target {target} is outside project_root {project_root}"
            ) from exc
        return f"res://{rel.as_posix()}"
    return f"res://{target_path.as_posix()}"


def _v1_argv(_target: str | None, project_root: Path) -> list[str]:
    """项目级检查：忽略 target，固定扫描哨兵脚本。"""
    return [
        "--headless",
        "--path",
        str(project_root),
        "--check-only",
        "--script",
        SENTINEL_RES_PATH,
        "--quit",
    ]


def _v2_argv(target: str | None, project_root: Path) -> list[str]:
    """单文件检查：target 是相对 project_root 的路径或 res:// 路径。"""
    if target is None:
        raise ValueError("V2 requires a target file path")
    return [
        "--headless",
        "--path",
        str(project_root),
        "--script",
        _to_res_path(target, project_root),
        "--check-only",
        "--quit",
    ]


def _v3_argv(_target: str | None, project_root: Path) -> list[str]:
    """全项目导入 + class cache 重建。忽略 target。"""
    return [
        "--headless",
        "--path",
        str(project_root),
        "--editor",
        "--import",
        "--quit",
    ]


VERIFY_COMMANDS: dict[str, Callable[[str | None, Path], list[str]]] = {
    "V1": _v1_argv,
    "V2": _v2_argv,
    "V3": _v3_argv,
}
