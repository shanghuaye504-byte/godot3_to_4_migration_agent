"""Heading path stack helper.

Specification: rag/vault/tier_b_prose/CHUNKING.md §4.5
"""

from __future__ import annotations


class HeadingPath:
    """Maintain a stack of section titles keyed by heading level.

    ``enter(title, level)`` pushes a new heading after popping any deeper or
    equal levels (so a sibling ``h2`` replaces the previous ``h2``).
    ``exit(level)`` pops until nothing at ``level`` or deeper remains.
    ``current()`` returns the ancestor titles as ``list[str]``.
    """

    def __init__(self) -> None:
        self._stack: list[tuple[int, str]] = []

    def enter(self, title: str, level: int) -> None:
        title = title.strip()
        if not title:
            return
        while self._stack and self._stack[-1][0] >= level:
            self._stack.pop()
        self._stack.append((level, title))

    def exit(self, level: int) -> None:
        while self._stack and self._stack[-1][0] >= level:
            self._stack.pop()

    def current(self) -> list[str]:
        return [title for _, title in self._stack]
