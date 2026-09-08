"""`[autoload]` 解析 —— 方案文档 §8。输入 `project.godot` 全文，不要起 Godot 去读。

规则：
1. 找到行首 `[autoload]`（允许前后空白）。
2. 读到下一个 `^[` 或 EOF。
3. 忽略空行与 `;` / `#` 开头的注释。
4. 匹配 `^(?P<key>[A-Za-z_][A-Za-z0-9_]*)\\s*=\\s*.+$`。
5. 只返回 key 的 frozenset。

N02 derived patch 实测值含 `uid://`，所以**不要**断言值必须是 `res://`——key 才是白名单。
插件未启用时 `[autoload]` 不存在 → 空集 → R2（autoload_fp）不删任何 Identifier-not-found，
这是正确行为，不是漏过滤。
"""

from __future__ import annotations

import re

_SECTION_HEADER = re.compile(r"^\[(?P<name>[^\]]*)\]\s*$")
_AUTOLOAD_KEY = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*.+$")


def parse_autoload_keys(project_godot_text: str) -> frozenset[str]:
    """解析 `project.godot` 的 `[autoload]` 段，返回全部 key 的 frozenset。

    找不到 `[autoload]` 段时返回空集，不抛异常（缺失是合法状态，见模块 docstring）。
    """
    lines = project_godot_text.splitlines()
    keys: set[str] = set()
    in_autoload_section = False

    for raw_line in lines:
        line = raw_line.strip()

        header_match = _SECTION_HEADER.match(line)
        if header_match:
            in_autoload_section = header_match.group("name") == "autoload"
            continue

        if not in_autoload_section:
            continue

        if not line or line.startswith(";") or line.startswith("#"):
            continue

        key_match = _AUTOLOAD_KEY.match(line)
        if key_match:
            keys.add(key_match.group("key"))

    return frozenset(keys)
