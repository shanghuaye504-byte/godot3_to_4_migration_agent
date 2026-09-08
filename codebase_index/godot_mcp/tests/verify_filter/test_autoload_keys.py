"""`autoload.py` 的纯函数测试（方案文档 §8）。

覆盖要点：
- 正常 `[autoload]` 段能解析出全部 key（用 `fixtures/godot_4_7_1/project_godot_with_autoload.ini`）。
- 值可以是 `res://` 也可以是 `uid://`（N02 derived patch 实测值）——**不要**断言值必须以
  `res://` 开头，key 才是白名单。
- 忽略空行与 `;`/`#` 开头的注释。
- 读到下一个 `^[` 或 EOF 就停止，不会把后续 section 的内容误吞进来。
- `project.godot` 里根本没有 `[autoload]` 段时返回空 frozenset，不抛异常。
"""

from __future__ import annotations

from godot_mcp.verify_filter.autoload import parse_autoload_keys


def test_parses_both_res_and_uid_style_values(load_fixture):
    text = load_fixture("project_godot_with_autoload.ini")
    keys = parse_autoload_keys(text)
    assert keys == frozenset({"Config", "DummySingleton"})


def test_ignores_comments_and_blank_lines():
    text = """
[autoload]

; 这是注释
Config="*res://config.gd"
# 这也是注释

DummySingleton="*uid://qmfp8cu17gl2"
"""
    assert parse_autoload_keys(text) == frozenset({"Config", "DummySingleton"})


def test_stops_at_next_section_header():
    text = """
[autoload]
Config="*res://config.gd"

[editor_plugins]
enabled=PackedStringArray("res://addons/dummy/plugin.cfg")
"""
    keys = parse_autoload_keys(text)
    assert keys == frozenset({"Config"})
    assert "enabled" not in keys


def test_missing_autoload_section_returns_empty_set():
    text = """
[application]
config/name="NoAutoloadHere"
"""
    assert parse_autoload_keys(text) == frozenset()


def test_empty_project_godot_returns_empty_set():
    assert parse_autoload_keys("") == frozenset()
