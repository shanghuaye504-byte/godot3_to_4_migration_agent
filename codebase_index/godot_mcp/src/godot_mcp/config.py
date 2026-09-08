"""共享配置读取 —— godot_mcp 这一侧只取它需要的两个字段。

与 `../index/src/codeindex/config.py` 读的是**同一份** `../config.yaml`
（design.md 6.4：两个子系统共享一份配置，避免各自硬编码路径后来对不上）。
但 yaml 里的字段不是两边对等消费的，按 `../README.md` 的字段表：

| 字段 | 谁用 |
| --- | --- |
| `project_root` | 两边都用（daemon 扫描根 == verify 工作目录） |
| `index_state_dir` | 仅 Layer 2（index/），Layer 3 现在用不到 |
| `godot_binary` | 仅 Layer 3（本文件） |
| `lsp_ports` | ~~已删除~~（LSP 方案整体移除） |

所以本文件**不**声明 `index_state_dir` / `lsp_ports` / `db_path` 这些不属于当前
范围的字段 —— 那是 `codeindex.config.Config` 的职责，两份 Config 分别只暴露各自
用得到的字段，即使读的是同一份 yaml 也不要互相 import 对方的 Config 类
（两个包运行时完全独立进程）。

路径定位方式与 index/ 侧保持同一套约定（从本文件往上数到 codebase_index/）：

    本文件位置
      godot_mcp/src/godot_mcp/config.py
        └── parents[3] = codebase_index/
              └── /config.yaml          ← 用户手填；可用 load_config(path=...) 覆盖

`CODEBASE_PROJECT_ROOT` 环境变量可覆盖 yaml 里的 `project_root`（与 index/ 侧同名同语义，
CI 换项目时两边只需设一次环境变量，不需要分别改 yaml）。

本文件只读 yaml、不起子进程、不做任何网络/进程副作用。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

# 默认 yaml 路径：从本文件往上数 3 层，落到 codebase_index/config.yaml
# （godot_mcp/src/godot_mcp/ -> godot_mcp/src/ -> godot_mcp/ -> codebase_index/）。
# 测试时应传入 path= 临时 yaml，不要依赖这份默认路径。
_CONFIG_SEARCH_PATH = Path(__file__).resolve().parents[3] / "config.yaml"

_DEFAULT_GODOT_BINARY = "godot4"


@dataclass(frozen=True)
class Config:
    """一次 load_config() 读出来的不可变快照，只含 Layer 3 用得到的字段。"""

    project_root: Path
    """校验子进程的工作目录。与 index/ 侧扫描的是同一个目录。"""
    godot_binary: str
    """Godot 4 可执行文件名或绝对路径（需在 PATH 中，或写绝对路径）。"""


def load_config(path: Path | None = None) -> Config:
    """读 yaml，拼出只含 Layer 3 字段的 Config。只读，不创建任何目录或文件。

    文件缺失 → 抛 FileNotFoundError；`project_root` 缺失 → 抛 KeyError
    （与 codeindex.config.load_config 的报错语义保持一致，server.py 顶层捕获后
    给出明确的"配置未就绪"错误，而不是裸 Traceback）。

    `godot_binary` 缺省时取 `_DEFAULT_GODOT_BINARY`。
    `CODEBASE_PROJECT_ROOT` 环境变量优先于 yaml 里的 `project_root`。
    """
    config_path = path or _CONFIG_SEARCH_PATH
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise KeyError(f"config must be a mapping: {config_path}")

    env_root = os.environ.get("CODEBASE_PROJECT_ROOT")
    if env_root:
        project_root = Path(env_root)
    elif "project_root" in raw:
        project_root = Path(raw["project_root"])
    else:
        raise KeyError("project_root")

    godot_binary = str(raw.get("godot_binary") or _DEFAULT_GODOT_BINARY)
    return Config(
        project_root=project_root.expanduser().resolve(),
        godot_binary=godot_binary,
    )
