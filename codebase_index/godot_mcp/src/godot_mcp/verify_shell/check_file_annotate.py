"""`check_file` 在 filter/merge 之后、Gate 之前的外壳标注（类别 A/B）。

过滤器不动：不删 `not declared`，不把非白名单 `Identifier not found` 当确定 FP。
`check_workspace` 不调用本模块。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from godot_mcp.verify_filter.models import ClassifiedEvent, ProjectFilterView
from godot_mcp.verify_shell.class_cache import class_cache_is_stale

CAVEAT_CLASS_CACHE_STALE = "class_cache_stale"
_UNREGISTERED_AUTOLOAD_PREFIX = "identifier_not_found_maybe_unregistered_autoload:"

DIRECTIVE_CLASS_CACHE_STALE = (
    "检测到 .godot/global_script_class_cache.cfg 与磁盘 class_name 不一致。"
    "请先调用 check_workspace（会按触发表 import 刷新全局类缓存），"
    "不要根据当前 Identifier not found / not declared 去改脚本。"
)
DIRECTIVE_UNREGISTERED_AUTOLOAD = (
    "根因里的 Identifier not found 可能是未写入 project.godot [autoload] 的插件单例。"
    "请先读取 [autoload] 白名单，必要时再 check_workspace；"
    "确认不是未登记单例之后，再改引用该符号的脚本。"
)


def caveat_unregistered_autoload(symbol: str) -> str:
    return f"{_UNREGISTERED_AUTOLOAD_PREFIX}{symbol}"


@dataclass(frozen=True)
class CheckFileAnnotation:
    view: ProjectFilterView
    directive: str | None


def annotate_check_file_view(
    view: ProjectFilterView,
    *,
    project_root: Path,
    autoload_keys: frozenset[str],
) -> CheckFileAnnotation:
    """按 class cache 是否陈旧，把 Identifier 假阳性移出可执行根因，或给漏网单例打 caveat。"""
    stale = class_cache_is_stale(project_root)
    demote: list[ClassifiedEvent] = []
    keep: list[ClassifiedEvent] = []
    for event in view.root_cause_errors:
        if stale and _is_identifier_shape(event, autoload_keys):
            demote.append(event)
        else:
            keep.append(event)

    caveats = list(view.caveats)
    if stale and CAVEAT_CLASS_CACHE_STALE not in caveats:
        caveats.append(CAVEAT_CLASS_CACHE_STALE)

    untrusted = view.untrusted_files
    if demote:
        extra = {event.res_path for event in demote if event.res_path}
        untrusted = untrusted | extra

    for symbol in _remaining_compile_identifier_symbols(keep, autoload_keys):
        caveat = caveat_unregistered_autoload(symbol)
        if caveat not in caveats:
            caveats.append(caveat)

    status = "HAS_ERRORS" if keep else "CLEAN"
    gdscript_complete = (not keep) and (not view.pending_pointers)
    if demote:
        directive: str | None = DIRECTIVE_CLASS_CACHE_STALE
    elif any(item.startswith(_UNREGISTERED_AUTOLOAD_PREFIX) for item in caveats):
        directive = DIRECTIVE_UNREGISTERED_AUTOLOAD
    else:
        directive = None

    return CheckFileAnnotation(
        view=replace(
            view,
            status=status,
            root_cause_errors=keep,
            caveats=caveats,
            untrusted_files=untrusted,
            gdscript_complete=gdscript_complete,
        ),
        directive=directive,
    )


def merge_shell_directive(
    *,
    hard_stop: bool,
    gate_directive: str | None,
    shell_directive: str | None,
) -> str | None:
    if hard_stop:
        return None
    if gate_directive:
        return gate_directive
    return shell_directive


def _is_parse_identifier(event: ClassifiedEvent) -> bool:
    symbol = event.symbol
    return (
        event.kind == "parse_error"
        and bool(symbol)
        and event.message == f'Parse Error: Identifier "{symbol}" not declared in the current scope.'
    )


def _is_compile_identifier(event: ClassifiedEvent, autoload_keys: frozenset[str]) -> bool:
    symbol = event.symbol
    return (
        bool(symbol)
        and symbol not in autoload_keys
        and event.message == f"Compile Error: Identifier not found: {symbol}"
    )


def _is_identifier_shape(event: ClassifiedEvent, autoload_keys: frozenset[str]) -> bool:
    return _is_parse_identifier(event) or _is_compile_identifier(event, autoload_keys)


def _remaining_compile_identifier_symbols(
    events: list[ClassifiedEvent],
    autoload_keys: frozenset[str],
) -> list[str]:
    symbols = {
        event.symbol
        for event in events
        if event.symbol and _is_compile_identifier(event, autoload_keys)
    }
    return sorted(symbols)
