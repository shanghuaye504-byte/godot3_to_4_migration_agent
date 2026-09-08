"""扩展名 → parser 的映射表。

这是明确标出的唯一扩展点（design.md 6.3）：以后支持第四种语言，
只在本文件的 _REGISTRY 加一行映射，其余代码不应因此改动。
"""

from __future__ import annotations

from pathlib import Path

from .base import Parser
from .cpp import CppParser
from .csharp import CSharpParser
from .gdscript import GdscriptParser

_REGISTRY: dict[str, tuple[str, Parser]] = {
    ".gd": ("gdscript", GdscriptParser()),
    ".cs": ("csharp", CSharpParser()),
    ".cpp": ("cpp", CppParser()),
    ".h": ("cpp", CppParser()),
    ".hpp": ("cpp", CppParser()),
}


def get_parser(path: Path) -> Parser | None:
    entry = _REGISTRY.get(path.suffix.lower())
    return entry[1] if entry else None


def language_of(path: Path) -> str:
    entry = _REGISTRY.get(path.suffix.lower())
    return entry[0] if entry else "unknown"


def supported_suffixes() -> tuple[str, ...]:
    return tuple(_REGISTRY)
