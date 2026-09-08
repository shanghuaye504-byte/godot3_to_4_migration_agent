"""config.py：读 yaml、环境变量覆盖、缺省值。不依赖 LSP / 子进程。

覆盖要点（实现时对照 `../src/godot_mcp/config.py` 的 docstring 逐条落）：
- 正常读两个字段（project_root / godot_binary），路径做 expanduser+resolve
- `godot_binary` 缺省 → "godot4"
- `CODEBASE_PROJECT_ROOT` 环境变量覆盖 yaml 里的 project_root（与 index/ 侧同名同语义）
- yaml 文件不存在 → 抛 FileNotFoundError
- yaml 里缺 project_root（且未设环境变量）→ 抛 KeyError

测试一律传临时 yaml（`tmp_path`），不读仓库里的 `../config.yaml`，
避免测试结果依赖开发者本机那份因人而异的配置。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from godot_mcp.config import load_config


def _write_yaml(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_load_config_reads_two_fields(tmp_path: Path) -> None:
    project = tmp_path / "game"
    cfg_path = _write_yaml(
        tmp_path / "config.yaml",
        {"project_root": str(project), "godot_binary": "/opt/godot4"},
    )

    cfg = load_config(cfg_path)

    assert cfg.project_root == project.resolve()
    assert cfg.godot_binary == "/opt/godot4"


def test_godot_binary_defaults_to_godot4(tmp_path: Path) -> None:
    project = (tmp_path / "game").resolve()
    cfg_path = _write_yaml(tmp_path / "config.yaml", {"project_root": str(project)})

    cfg = load_config(cfg_path)

    assert cfg.project_root == project
    assert cfg.godot_binary == "godot4"


def test_env_overrides_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    yaml_root = tmp_path / "from-yaml"
    env_root = (tmp_path / "from-env").resolve()
    cfg_path = _write_yaml(tmp_path / "config.yaml", {"project_root": str(yaml_root)})
    monkeypatch.setenv("CODEBASE_PROJECT_ROOT", str(env_root))

    cfg = load_config(cfg_path)

    assert cfg.project_root == env_root


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "no-such.yaml")


def test_missing_project_root_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODEBASE_PROJECT_ROOT", raising=False)
    cfg_path = _write_yaml(tmp_path / "config.yaml", {"godot_binary": "godot4"})
    with pytest.raises(KeyError, match="project_root"):
        load_config(cfg_path)
