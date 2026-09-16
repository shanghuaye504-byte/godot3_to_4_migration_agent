"""磁盘 `class_name` 与 `.godot/global_script_class_cache.cfg` 对比。

只给 `check_file` 外壳标注用。禁止对 `check_file` 调用 `scan_workspace`
（会撞 2000/1GiB 硬拒）。本模块不起 Godot、不改缓存。
"""

from __future__ import annotations

import re
from pathlib import Path

from godot_mcp.verify_shell.cache import CLASS_CACHE_REL
from godot_mcp.verify_shell.snapshot import SKIP_DIRS

CLASS_NAME_DECL = re.compile(r"^class_name\s+(\S+)")
_CACHE_OBJECT = re.compile(r"\{[^{}]*\}")
_CACHE_CLASS = re.compile(r'"class"\s*:\s*&?"([^"]+)"')
_CACHE_PATH = re.compile(r'"path"\s*:\s*&?"([^"]+)"')


def scan_disk_global_classes(project_root: Path) -> frozenset[tuple[str, str]]:
    """每个 `.gd` 只取第一行匹配的 `class_name`。跳过 `SKIP_DIRS`。

    返回 `(class_name, res://相对 posix)`。`# class_name X` 不匹配行首。
    `class_name Foo extends Node` 由 `\\S+` 只吃到 `Foo`。
    """
    root = Path(project_root)
    found: set[tuple[str, str]] = set()
    if not root.is_dir():
        return frozenset()
    for path in root.rglob("*.gd"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            match = CLASS_NAME_DECL.match(line)
            if match:
                found.add((match.group(1), _as_res(rel.as_posix())))
                break
    return frozenset(found)


def parse_class_cache(text: str) -> frozenset[tuple[str, str]]:
    """按对象块配对 `class`/`path`，禁止把全文 class 与 path 全局 zip。

    同时接受 `&"ProbeFoo"` 与 `"ProbeFoo"`。`list=[]` 或无 `{...}` 块 → 空集。
    """
    pairs: set[tuple[str, str]] = set()
    for block in _CACHE_OBJECT.findall(text):
        class_match = _CACHE_CLASS.search(block)
        path_match = _CACHE_PATH.search(block)
        if class_match and path_match:
            pairs.add((class_match.group(1), _as_res(path_match.group(1))))
    return frozenset(pairs)


def class_cache_is_stale(project_root: Path) -> bool:
    """磁盘全局类集合是否与 class cache 不一致（增 / 改名 / 挪路径 / 删）。

    - 缓存文件不存在：磁盘也无 `class_name` → `False`；磁盘有全局类 → `True`。
    - 文件存在：正文含 `"class":` 但解析为空集 → 视为解析失败，返回 `True`。
      `list=[]` 不含 `"class":`，与空磁盘比较为 `False`。
    """
    root = Path(project_root)
    disk = scan_disk_global_classes(root)
    cache_path = root / CLASS_CACHE_REL
    if not cache_path.is_file():
        return bool(disk)
    text = cache_path.read_text(encoding="utf-8", errors="replace")
    parsed = parse_class_cache(text)
    if '"class":' in text and not parsed:
        return True
    return parsed != disk


def _as_res(path: str) -> str:
    if path.startswith("res://"):
        return path
    return f"res://{path}"
