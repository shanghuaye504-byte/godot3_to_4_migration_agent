"""按 YAML 中的 hooks 名称分派到具体 hook 模块。

契约：每个 hook 模块导出 `apply(workspace, *, context, **kwargs) -> Optional[Callable[[], None]]`。
返回的可调用对象（若非 None）会在步骤结束后被调用以撤销该 hook 的效果。
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


class HookError(Exception):
    pass


@dataclass
class HookInvocation:
    name: str
    revert: Optional[Callable[[], None]] = None


def _load_hook_module(name: str):
    try:
        return importlib.import_module(f".{name}", package=__package__)
    except ImportError as exc:
        raise HookError(f"未知 hook: {name}") from exc


def apply_hooks(hook_specs: list, *, workspace: Path, context: dict) -> list:
    invocations = []
    for spec in hook_specs:
        module = _load_hook_module(spec.name)
        apply_fn = getattr(module, "apply", None)
        if apply_fn is None:
            raise HookError(f"hook {spec.name} 未实现 apply()")
        revert = apply_fn(workspace, context=context, **spec.args)
        invocations.append(HookInvocation(name=spec.name, revert=revert if callable(revert) else None))
    return invocations


def revoke_hooks(invocations: list) -> None:
    for invocation in reversed(invocations):
        if invocation.revert is not None:
            invocation.revert()
