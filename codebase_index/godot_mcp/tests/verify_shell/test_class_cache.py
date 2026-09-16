"""`class_cache`：解析 Godot 4 cache 对象块，对比磁盘 `class_name`。"""

from __future__ import annotations

from pathlib import Path

from godot_mcp.verify_shell.cache import CLASS_CACHE_REL
from godot_mcp.verify_shell.class_cache import (
    class_cache_is_stale,
    parse_class_cache,
    scan_disk_global_classes,
)


def _write_class_cache(tmp_path: Path, entries: list[tuple[str, str]]) -> None:
    dest = tmp_path / CLASS_CACHE_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not entries:
        dest.write_text("list=[]\n", encoding="utf-8")
        return
    chunks: list[str] = []
    for name, path in entries:
        res = path if path.startswith("res://") else f"res://{path}"
        chunks.append(
            "{\n"
            '"base": &"RefCounted",\n'
            f'"class": &"{name}",\n'
            f'"path": "{res}"\n'
            "}"
        )
    dest.write_text("list=[" + ",".join(chunks) + "]\n", encoding="utf-8")


def test_parse_empty_list_is_empty() -> None:
    assert parse_class_cache("list=[]\n") == frozenset()


def test_parse_ampersand_string_name() -> None:
    text = (
        "list=[{\n"
        '"base": &"RefCounted",\n'
        '"class": &"Foo",\n'
        '"path": "res://foo.gd"\n'
        "}]\n"
    )
    assert parse_class_cache(text) == frozenset({("Foo", "res://foo.gd")})


def test_parse_plain_quoted_class() -> None:
    text = '{"class": "Foo", "path": "res://foo.gd"}'
    assert parse_class_cache(text) == frozenset({("Foo", "res://foo.gd")})


def test_parse_two_objects_swapped_key_order() -> None:
    text = (
        "list=["
        '{"path": "res://a.gd", "class": &"A"},'
        '{"class": "B", "path": "res://b.gd"}'
        "]"
    )
    assert parse_class_cache(text) == frozenset(
        {("A", "res://a.gd"), ("B", "res://b.gd")}
    )


def test_parse_path_without_res_prefix_is_normalized() -> None:
    text = '{"class": "Foo", "path": "foo.gd"}'
    assert parse_class_cache(text) == frozenset({("Foo", "res://foo.gd")})


def test_scan_class_name_extends_only_takes_name(tmp_path: Path) -> None:
    (tmp_path / "foo.gd").write_text("class_name Foo extends Node\n", encoding="utf-8")
    assert scan_disk_global_classes(tmp_path) == frozenset({("Foo", "res://foo.gd")})


def test_scan_commented_class_name_ignored(tmp_path: Path) -> None:
    (tmp_path / "foo.gd").write_text("# class_name Hidden\nextends Node\n", encoding="utf-8")
    assert scan_disk_global_classes(tmp_path) == frozenset()


def test_scan_first_matching_line_only(tmp_path: Path) -> None:
    (tmp_path / "foo.gd").write_text(
        "extends Node\nclass_name First\nclass_name Second\n",
        encoding="utf-8",
    )
    assert scan_disk_global_classes(tmp_path) == frozenset({("First", "res://foo.gd")})


def test_git_hidden_class_name_not_scanned(tmp_path: Path) -> None:
    git = tmp_path / ".git"
    git.mkdir()
    (git / "hidden.gd").write_text("class_name Hidden\n", encoding="utf-8")
    _write_class_cache(tmp_path, [])
    assert scan_disk_global_classes(tmp_path) == frozenset()
    assert class_cache_is_stale(tmp_path) is False


def test_godot_dir_class_name_not_scanned(tmp_path: Path) -> None:
    hidden = tmp_path / ".godot"
    hidden.mkdir()
    (hidden / "hidden.gd").write_text("class_name Hidden\n", encoding="utf-8")
    _write_class_cache(tmp_path, [])
    assert class_cache_is_stale(tmp_path) is False


def test_stale_when_disk_adds_class(tmp_path: Path) -> None:
    (tmp_path / "foo.gd").write_text("class_name Foo\n", encoding="utf-8")
    _write_class_cache(tmp_path, [])
    assert class_cache_is_stale(tmp_path) is True


def test_stale_when_renamed(tmp_path: Path) -> None:
    (tmp_path / "foo.gd").write_text("class_name Bar\n", encoding="utf-8")
    _write_class_cache(tmp_path, [("Foo", "res://foo.gd")])
    assert class_cache_is_stale(tmp_path) is True


def test_stale_when_same_name_moved_path(tmp_path: Path) -> None:
    (tmp_path / "other.gd").write_text("class_name Foo\n", encoding="utf-8")
    _write_class_cache(tmp_path, [("Foo", "res://foo.gd")])
    assert class_cache_is_stale(tmp_path) is True


def test_stale_when_declaration_deleted(tmp_path: Path) -> None:
    (tmp_path / "foo.gd").write_text("extends Node\n", encoding="utf-8")
    _write_class_cache(tmp_path, [("Foo", "res://foo.gd")])
    assert class_cache_is_stale(tmp_path) is True


def test_consistent_name_and_path_not_stale(tmp_path: Path) -> None:
    (tmp_path / "probe_foo.gd").write_text("class_name ProbeFoo\n", encoding="utf-8")
    _write_class_cache(tmp_path, [("ProbeFoo", "res://probe_foo.gd")])
    assert class_cache_is_stale(tmp_path) is False


def test_missing_cache_without_class_name_not_stale(tmp_path: Path) -> None:
    (tmp_path / "a.gd").write_text("extends Node\n", encoding="utf-8")
    assert not (tmp_path / CLASS_CACHE_REL).exists()
    assert class_cache_is_stale(tmp_path) is False


def test_missing_cache_with_class_name_is_stale(tmp_path: Path) -> None:
    (tmp_path / "foo.gd").write_text("class_name Foo\n", encoding="utf-8")
    assert class_cache_is_stale(tmp_path) is True


def test_malformed_class_field_without_pairing_is_stale(tmp_path: Path) -> None:
    dest = tmp_path / CLASS_CACHE_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text('list=["class": "Broken"]\n', encoding="utf-8")
    assert parse_class_cache(dest.read_text(encoding="utf-8")) == frozenset()
    assert class_cache_is_stale(tmp_path) is True


def test_object_missing_path_is_stale(tmp_path: Path) -> None:
    dest = tmp_path / CLASS_CACHE_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text('list=[{"class": "Foo"}]\n', encoding="utf-8")
    assert class_cache_is_stale(tmp_path) is True


def test_empty_list_matches_empty_disk(tmp_path: Path) -> None:
    _write_class_cache(tmp_path, [])
    assert class_cache_is_stale(tmp_path) is False
