"""unified diff 离线视图 —— 方案文档 §2.1.2。

V3 触发表只看 diff 文本，不起 Godot。空字符串视为「本轮没有 patch」。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PLUS_MINUS = re.compile(r"^[+-](?!\+\+ |--- )")


def _strip_prefix(path: str) -> str:
    path = path.strip()
    if path.startswith("b/") or path.startswith("a/"):
        return path[2:]
    return path


@dataclass(frozen=True)
class DiffView:
    """一次 patch 的路径与 hunk 摘要。"""

    added_paths: frozenset[str]
    deleted_paths: frozenset[str]
    changed_paths: frozenset[str]
    plus_minus_lines: tuple[str, ...]
    hunks_by_path: dict[str, str]

    def line_matches(self, pattern: re.Pattern[str]) -> bool:
        return any(pattern.search(line) for line in self.plus_minus_lines)

    def added_gd_file(self) -> bool:
        return any(path.endswith(".gd") for path in self.added_paths)

    def path_endswith(self, suffixes: tuple[str, ...]) -> bool:
        return any(path.endswith(suffixes) for path in self.all_paths())

    def tres_hunk_mentions_shader(self) -> bool:
        for path, hunk in self.hunks_by_path.items():
            if not path.endswith(".tres"):
                continue
            if ".gdshader" in hunk or "shader_type" in hunk:
                return True
        return False

    def deleted_uid(self) -> bool:
        return any(path.endswith(".uid") for path in self.deleted_paths)

    def all_paths(self) -> frozenset[str]:
        return self.added_paths | self.deleted_paths | self.changed_paths


def parse_unified_diff(text: str) -> DiffView:
    """解析 git / unified diff。解析失败时退回空视图，不抛。"""
    if not text or not text.strip():
        return DiffView(frozenset(), frozenset(), frozenset(), (), {})

    added: set[str] = set()
    deleted: set[str] = set()
    changed: set[str] = set()
    plus_minus: list[str] = []
    hunks: dict[str, list[str]] = {}
    current: str | None = None
    pending_new = False
    pending_del = False

    for line in text.splitlines():
        if line.startswith("diff --git "):
            current = None
            pending_new = False
            pending_del = False
            continue
        if line.startswith("new file mode"):
            pending_new = True
            continue
        if line.startswith("deleted file mode"):
            pending_del = True
            continue
        if line.startswith("--- "):
            old = _strip_prefix(line[4:])
            if old != "/dev/null" and pending_del:
                deleted.add(old)
                current = old
            continue
        if line.startswith("+++ "):
            new = _strip_prefix(line[4:])
            if new == "/dev/null":
                continue
            current = new
            if pending_new or line.endswith("/dev/null"):
                added.add(new)
            elif new not in deleted:
                changed.add(new)
            hunks.setdefault(new, [])
            pending_new = False
            continue
        if current is not None:
            hunks.setdefault(current, []).append(line)
        if _PLUS_MINUS.match(line):
            plus_minus.append(line)

    return DiffView(
        added_paths=frozenset(added),
        deleted_paths=frozenset(deleted),
        changed_paths=frozenset(changed - added - deleted),
        plus_minus_lines=tuple(plus_minus),
        hunks_by_path={path: "\n".join(lines) for path, lines in hunks.items()},
    )
