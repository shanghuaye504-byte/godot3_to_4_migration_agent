"""config.py：读 yaml、环境变量覆盖、派生路径。不依赖 SQLite / tree-sitter。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from codeindex.config import load_config


def _write_yaml(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_load_config_reads_four_fields_and_derived_paths(tmp_path: Path) -> None:
    project = tmp_path / "game"
    state = project / ".codeindex"
    cfg_path = _write_yaml(
        tmp_path / "config.yaml",
        {
            "project_root": str(project),
            "index_state_dir": str(state),
            "godot_binary": "godot4",
        },
    )

    cfg = load_config(cfg_path)

    assert cfg.project_root == project.resolve()
    assert cfg.index_state_dir == state.resolve()
    assert cfg.godot_binary == "godot4"
    assert cfg.db_path == state.resolve() / "index.db"
    assert cfg.lock_path == state.resolve() / "daemon.lock"
    assert cfg.ready_path == state.resolve() / "ready"


def test_missing_index_state_dir_defaults_under_project_root(tmp_path: Path) -> None:
    project = (tmp_path / "game").resolve()
    cfg_path = _write_yaml(tmp_path / "config.yaml", {"project_root": str(project)})

    cfg = load_config(cfg_path)

    assert cfg.index_state_dir == project / ".codeindex"
    assert cfg.godot_binary == "godot4"


def test_env_overrides_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    yaml_root = tmp_path / "from-yaml"
    env_root = (tmp_path / "from-env").resolve()
    cfg_path = _write_yaml(tmp_path / "config.yaml", {"project_root": str(yaml_root)})
    monkeypatch.setenv("CODEBASE_PROJECT_ROOT", str(env_root))

    cfg = load_config(cfg_path)

    assert cfg.project_root == env_root
    assert cfg.index_state_dir == env_root / ".codeindex"


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "no-such.yaml")
