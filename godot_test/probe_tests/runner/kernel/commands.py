"""V1-V10 与 PROJECT_CHECK 解析。

把 YAML 里的 command 别名展开成完整 argv；字面 V1..V10 永远走各自的模板，
不查 capabilities。PROJECT_CHECK 由 N08 导出的 command-capabilities.json
解析为 V1/V9/V10（该导出尚不存在，resolve_project_check 只提供接口）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from .types import EngineProfile


class CommandProfileError(Exception):
    pass


@dataclass(frozen=True)
class ArgvTemplate:
    name: str
    template: list
    requires: list


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


@dataclass(frozen=True)
class CommandCapabilities:
    preferred: str
    reason: str = ""


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
    capabilities: Optional[CommandCapabilities] = None,
) -> list:
    extra_flags = extra_flags or []

    if alias == "PROJECT_CHECK":
        return resolve_project_check(
            capabilities,
            profiles=profiles,
            engine_profile=engine_profile,
            project_path=project_path,
        )

    if alias == "V10":
        gd_files = sorted(
            p for p in Path(project_path).rglob("*.gd") if not p.name.startswith("__probe_")
        )
        v2 = profiles.get("V2")
        if v2 is None:
            raise CommandProfileError("V10 需要 V2 模板但未加载")
        return [
            list(engine_profile.executable)
            + _expand_template(v2.template, path=str(project_path), script=gd.name)
            + extra_flags
            for gd in gd_files
        ]

    template = profiles.get(alias)
    if template is None:
        raise CommandProfileError(f"未知指令别名: {alias}")
    argv = _expand_template(template.template, path=str(project_path), script=script)
    return list(engine_profile.executable) + argv + extra_flags


def resolve_project_check(
    capabilities: Optional[CommandCapabilities],
    *,
    profiles: dict,
    engine_profile: EngineProfile,
    project_path: Path,
) -> list:
    if capabilities is None:
        raise CommandProfileError(
            "PROJECT_CHECK 需要 N08 导出的 command-capabilities.json，尚未产出"
        )
    if capabilities.preferred not in ("V1", "V9", "V10"):
        raise CommandProfileError(f"非法 PROJECT_CHECK preferred: {capabilities.preferred}")
    return resolve_command(
        capabilities.preferred,
        profiles=profiles,
        engine_profile=engine_profile,
        project_path=project_path,
    )
