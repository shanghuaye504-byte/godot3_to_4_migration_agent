"""Parser 协议：所有语言解析器统一的输入输出契约。

to_name / base_name 一律存原始文本（不做静态解析绑定），理由见 design.md 2.7。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str  # class / func / signal / var / const / enum
    line: int  # 0-based
    end_line: int
    class_name: str | None
    signature: str | None


@dataclass(frozen=True)
class Edge:
    from_symbol: str
    to_name: str  # 原始文本，查询时 JOIN 解析
    line: int
    kind: str  # call / extends / preload


@dataclass(frozen=True)
class ClassDecl:
    name: str
    base_name: str | None  # extends 的原始文本
    line: int


@dataclass
class ParseResult:
    symbols: list[Symbol] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    class_decl: ClassDecl | None = None  # 每文件至多一个主 class 声明


class Parser(Protocol):
    def parse(self, path: str, source: str) -> ParseResult:
        """解析单个文件。语法错误时应抛异常（writer 会捕获并记 failed）。"""
        ...
