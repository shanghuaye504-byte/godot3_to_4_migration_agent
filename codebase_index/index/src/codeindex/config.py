"""共享配置读取。

config.yaml 是用户手填的，系统不会生成。
仓库里只提交 config.example.yaml（占位模板）；使用方复制成 config.yaml，
填入自己那份 Godot 项目的路径。config.yaml 已 gitignore，因为路径因人/因项目而异。

系统后来会自动创建的是 index_state_dir 里面的运行时文件
（index.db / daemon.lock / ready），那是 daemon 跑起来之后写的，不是这份 yaml。

    本文件位置
      index/src/codeindex/config.py
        └── parents[3] = codebase_index/
              └── /config.yaml          ← 用户手填；可用 load_config(path=...) 覆盖

    yaml 或环境变量
      CODEBASE_PROJECT_ROOT 优先，否则 yaml["project_root"]
        └── project_root                ← 被索引的 Godot 工程根（不是本仓库）

    yaml["index_state_dir"] 若缺省
      project_root / ".codeindex"
        └── index_state_dir             ← 运行时产物目录

    三个派生路径（调用方不要手写文件名）
      index_state_dir / "index.db"      → db_path
      index_state_dir / "daemon.lock"   → lock_path
      index_state_dir / "ready"         → ready_path

index/ 与 godot_mcp/ 都读这一份 yaml，避免两边硬编码路径后来对不上。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

# 默认 yaml 路径：从本文件往上数 3 层，落到 codebase_index/config.yaml。
#
#   parents[0] = .../index/src/codeindex/     本包目录
#   parents[1] = .../index/src/
#   parents[2] = .../index/
#   parents[3] = .../codebase_index/          与 config.example.yaml 同级
#
# 测试时应传入 path= 临时 yaml，不要依赖这份默认路径。
_CONFIG_SEARCH_PATH = Path(__file__).resolve().parents[3] / "config.yaml"


@dataclass(frozen=True)
class Config:
    """一次 load_config() 读出来的不可变快照。yaml 本身不会被这个类写回去。"""

    project_root: Path
    """被索引/被验证的 Godot 项目根目录。daemon 扫这里，verify 也以此为工作目录。"""
    index_state_dir: Path
    """运行时状态目录。约定为 project_root/.codeindex/，里面是系统生成的文件，不是用户填的。"""
    godot_binary: str
    """Godot 4 可执行文件名或绝对路径。仅 Layer 3 用；Layer 2 读进来是为了和 MCP 共用一份配置。"""
    # SCENE_INDEX_TODO(step4-rules-db): 见 codebase_index/NEXT_STEP.md 第 7 节开头的「标记」说明。
    # 实现时增加可选字段 migration_rules_db。缺省时场景校验不报 E_UNMIGRATED_TYPE。
    # godot_mcp 读同一份 yaml 时忽略未知键，不要改那边的 Config。

    @property
    def db_path(self) -> Path:
        """SQLite 索引库。= index_state_dir / 'index.db'，由 daemon 首次扫描时创建。"""
        return self.index_state_dir / "index.db"

    @property
    def lock_path(self) -> Path:
        """daemon 单例锁。= index_state_dir / 'daemon.lock'，daemon 启动时创建。"""
        return self.index_state_dir / "daemon.lock"

    @property
    def ready_path(self) -> Path:
        """全量扫描完成标记。= index_state_dir / 'ready'，daemon 扫完才写；codeindex up 轮询它。"""
        return self.index_state_dir / "ready"


def load_config(path: Path | None = None) -> Config:
    """读 yaml，拼出 Config。只读，不创建任何目录或文件。

    文件缺失或必填字段缺失时抛异常（CLI 顶层捕获后以退出码 2 报错）。
    """
    # 1) 定位 yaml：调用方显式传入 > 仓库约定的 codebase_index/config.yaml
    config_path = path or _CONFIG_SEARCH_PATH
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise KeyError(f"config must be a mapping: {config_path}")

    # 2) 拼 project_root：环境变量整段替换 yaml 里的值（CI 换仓库时不必改文件）
    env_root = os.environ.get("CODEBASE_PROJECT_ROOT")
    if env_root:
        project_root = Path(env_root)
    elif "project_root" in raw:
        project_root = Path(raw["project_root"])
    else:
        raise KeyError("project_root")
    project_root = project_root.expanduser().resolve()

    # 3) 拼 index_state_dir：yaml 写了就用；没写则挂到 project_root/.codeindex
    #    （所以只设 CODEBASE_PROJECT_ROOT、yaml 又不写 index_state_dir 时，
    #     状态目录会跟着新的工程根走。）
    raw_state = raw.get("index_state_dir")
    if raw_state:
        index_state_dir = Path(raw_state).expanduser().resolve()
    else:
        index_state_dir = project_root / ".codeindex"

    # 4) 其余字段有缺省，不参与路径拼接
    return Config(
        project_root=project_root,
        index_state_dir=index_state_dir,
        godot_binary=str(raw.get("godot_binary") or "godot4"),
    )
