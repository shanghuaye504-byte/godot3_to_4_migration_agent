"""unified diff 解析：触发表依赖的几类路径。"""

from __future__ import annotations

from godot_mcp.verify_shell.diff import parse_unified_diff
from godot_mcp.verify_shell.trigger import CLASS_NAME_LINE


_NEW_GD = """\
diff --git a/late.gd b/late.gd
new file mode 100644
--- /dev/null
+++ b/late.gd
@@ -0,0 +1,2 @@
+extends Node
+class_name LateFoo
"""

_SHADER = """\
diff --git a/bad.gdshader b/bad.gdshader
--- a/bad.gdshader
+++ b/bad.gdshader
@@ -1 +1 @@
-shader_type canvas_item;
+shader_type canvas_item;
"""

_TRES_SHADER = """\
diff --git a/mat.tres b/mat.tres
--- a/mat.tres
+++ b/mat.tres
@@ -1 +1 @@
-shader_path="res://old.gdshader"
+shader_path="res://new.gdshader"
"""

_DEL_UID = """\
diff --git a/main.tscn.uid b/main.tscn.uid
deleted file mode 100644
--- a/main.tscn.uid
+++ /dev/null
@@ -1 +0,0 @@
-uid://abc
"""


def test_empty_diff() -> None:
    view = parse_unified_diff("")
    assert view.added_paths == frozenset()
    assert view.line_matches(CLASS_NAME_LINE) is False


def test_new_gd_and_class_name() -> None:
    view = parse_unified_diff(_NEW_GD)
    assert view.added_gd_file() is True
    assert view.line_matches(CLASS_NAME_LINE) is True


def test_shader_path_and_tres_hunk() -> None:
    assert parse_unified_diff(_SHADER).path_endswith((".gdshader", ".shader"))
    assert parse_unified_diff(_TRES_SHADER).tres_hunk_mentions_shader() is True


def test_deleted_uid() -> None:
    assert parse_unified_diff(_DEL_UID).deleted_uid() is True
