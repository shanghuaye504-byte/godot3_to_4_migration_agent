"""V1–V8 指令解析。

V1 是项目级编译校验：argv 指向 res://__probe_sentinel.gd。
哨兵文件由 kernel（runner）在步骤前写入、步骤后删除，不走配置映射。
PROJECT_CHECK 与 V1 同义。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from .types import EngineProfile

SENTINEL_RESOURCE = "res://__probe_sentinel.gd"
SENTINEL_COMMANDS = frozenset({"V1", "PROJECT_CHECK", "V7_V1", "V8_V1"})


class CommandProfileError(Exception):
    pass


@dataclass(frozen=True)
class ArgvTemplate:
    name: str
    template: list
    requires: list


def uses_sentinel(alias: str) -> bool:
    return alias in SENTINEL_COMMANDS


def load_command_profiles(common_dir: Path) -> dict:
    path = Path(common_dir) / "command-profiles.yaml"
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    commands = data.get("commands", {})
    profiles = {}
    for name, spec in commands.items():
        profiles[name] = ArgvTemplate(
            name=name,
            template=list(spec.get("argv", [])),
            requires=list(spec.get("requires", [])),
        )
    return profiles


def _expand_template(template: list, *, path: str, script: Optional[str]) -> list:
    argv = []
    for token in template:
        if "{path}" in token:
            token = token.replace("{path}", path)
        if "{script}" in token:
            if script is None:
                raise CommandProfileError("该指令模板需要 script 但未提供")
            token = token.replace("{script}", script)
        argv.append(token)
    return argv


def resolve_command(
    alias: str,
    *,
    profiles: dict,
    engine_profile: EngineProfile,
    project_path: Path,
    script: Optional[str] = None,
    extra_flags: Optional[list] = None,
) -> list:
    extra_flags = extra_flags or []
    if alias == "PROJECT_CHECK":
        alias = "V1"
    template = profiles.get(alias)
    if template is None:
        raise CommandProfileError(f"未知指令别名: {alias}")
    argv = _expand_template(template.template, path=str(project_path), script=script)
    return list(engine_profile.executable) + argv + extra_flags
