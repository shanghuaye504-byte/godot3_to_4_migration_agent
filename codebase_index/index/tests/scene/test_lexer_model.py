"""Step 1 的验收：L0 lexer + L1 model。

见 codebase_index/NEXT_STEP.md Step 1 与 scenecheckfixture/README.md
的「测试时怎样算通过」。预期以夹具 README 为准，契约以 NEXT_STEP 为准。
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from codeindex.scene import parse_scene
from codeindex.scene.lexer import (
    BlankLine,
    CommentLine,
    HeaderLine,
    PropLine,
    Value,
    lex_text,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "scenecheckfixture"

ALL_TSCN = sorted(FIXTURE_ROOT.rglob("*.tscn"))
REAL_DODGE = sorted(FIXTURE_ROOT.rglob("real_dodge_*.tscn"))
GODOT3_MATRIX = FIXTURE_ROOT / "godot3" / "generated_format_matrix.tscn"
GODOT4_MATRIX = FIXTURE_ROOT / "godot4" / "generated_format_matrix.tscn"

assert len(ALL_TSCN) == 8, f"夹具应有 8 个 .tscn，实际 {len(ALL_TSCN)}"
assert len(REAL_DODGE) == 6, f"夹具应有 6 个 real_dodge，实际 {len(REAL_DODGE)}"


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _line_col(text: str, pos: int) -> tuple[int, int]:
    """逐字节换行计数，与 span 的 line/col 对照。"""
    line = text.count("\n", 0, pos) + 1
    last_nl = text.rfind("\n", 0, pos)
    return line, pos - last_nl


def _read_raw(path: Path) -> str:
    """保留 CRLF 的读法。read_text() 会把 \\r\\n 归一成 \\n。"""
    return path.read_bytes().decode("utf-8")


def _check_value(text: str, v: Value, ctx: str) -> None:
    s = v.span
    assert text[s.byte_start : s.byte_end] == v.raw, (
        f"{ctx}: raw 与切片不一致 @{s.byte_start}:{s.byte_end} "
        f"raw={v.raw!r} slice={text[s.byte_start:s.byte_end]!r}"
    )
    line, col = _line_col(text, s.byte_start)
    assert s.line == line, f"{ctx}: line {s.line} != {line}"
    assert s.col == col, f"{ctx}: col {s.col} != {col}"
    for item in v.items:
        _check_value(text, item, ctx)
    for k, val in v.pairs:
        _check_value(text, k, ctx)
        _check_value(text, val, ctx)


def _all_values(doc):
    for s in doc.sections:
        for v in s.attrs.values():
            yield v
        for _, v in s.props:
            yield v


# ---------------------------------------------------------------------------
# 验收 1：span 切片等于原文；line/col 与逐字节换行计数一致
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ALL_TSCN, ids=lambda p: p.name)
def test_span_slice_and_line_col(path: Path) -> None:
    text = _read_raw(path)
    doc = parse_scene(text, str(path))
    for s in doc.sections:
        hs = s.heading_span
        assert text[hs.byte_start : hs.byte_end].startswith("[")
        line, col = _line_col(text, hs.byte_start)
        assert hs.line == line and hs.col == col
    for v in _all_values(doc):
        _check_value(text, v, f"{path.name}")


# ---------------------------------------------------------------------------
# 验收 2：去掉注释和空白后，每个字节都落在某个 span 里
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ALL_TSCN, ids=lambda p: p.name)
def test_byte_coverage(path: Path) -> None:
    text = _read_raw(path)
    n = len(text)
    covered = bytearray(n)
    result = lex_text(text)
    for line in result.lines:
        if isinstance(line, (BlankLine, CommentLine)):
            for i in range(line.span.byte_start, line.span.byte_end):
                covered[i] = 1
        elif isinstance(line, HeaderLine):
            for i in range(line.span.byte_start, line.span.byte_end):
                covered[i] = 1
        elif isinstance(line, PropLine):
            for i in range(line.name_span.byte_start, line.name_span.byte_end):
                covered[i] = 1
            _cover_value(line.value, covered)
    # 未覆盖的字节只允许是空白或 prop 的 `=` 与周围空格
    for i in range(n):
        if not covered[i]:
            assert text[i] in " \t\r\n=", (
                f"{path.name} 字节 {i} ({text[i]!r}) 不在任何 span 里，也不是空白/="
            )


def _cover_value(v: Value, covered: bytearray) -> None:
    for i in range(v.span.byte_start, v.span.byte_end):
        covered[i] = 1
    for item in v.items:
        _cover_value(item, covered)
    for k, val in v.pairs:
        _cover_value(k, covered)
        _cover_value(val, covered)


# ---------------------------------------------------------------------------
# 验收 3：六个 real_dodge 零语法错误
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", REAL_DODGE, ids=lambda p: p.name)
def test_real_dodge_zero_problems(path: Path) -> None:
    text = _read_raw(path)
    doc = parse_scene(text, str(path))
    assert doc.problems == [], f"{path.name} 有语法问题: {[(p.code, p.message) for p in doc.problems]}"


def test_real_dodge_format_versions() -> None:
    for path in REAL_DODGE:
        text = _read_raw(path)
        doc = parse_scene(text, str(path))
        if "godot3" in path.parts:
            assert doc.format == 2, f"{path.name} 应为 format=2"
        else:
            assert doc.format == 3, f"{path.name} 应为 format=3"
            assert doc.uid is not None and doc.uid.startswith("uid://")


# ---------------------------------------------------------------------------
# 验收 4：格式矩阵——godot3 generated
# ---------------------------------------------------------------------------


def test_godot3_matrix() -> None:
    text = _read_raw(GODOT3_MATRIX)
    doc = parse_scene(text, str(GODOT3_MATRIX))
    assert doc.problems == [], f"problems: {[(p.code, p.message) for p in doc.problems]}"
    assert doc.format == 2
    assert doc.doc_kind == "scene"

    kinds = [s.kind for s in doc.sections]
    assert kinds[0] == "gd_scene"
    assert "ext_resource" in kinds
    assert "node" in kinds

    # 整数 id
    ext = next(s for s in doc.sections if s.kind == "ext_resource")
    assert ext.attrs["id"].kind == "int"
    assert ext.attrs["id"].raw == "1"

    # 相对路径
    assert ext.attrs["path"].raw == '"icon.png"'

    # 根节点带 instance（继承场景）
    root = next(s for s in doc.sections if s.kind == "node")
    assert "instance" in root.attrs
    assert root.attrs["instance"].kind == "call"
    assert root.attrs["instance"].name == "ExtResource"

    # KinematicBody2D 不是语法错误
    body = next(s for s in doc.sections if s.attrs.get("name", Value("str", "", None)).raw == '"Body"')
    assert body.attrs["type"].raw == '"KinematicBody2D"'

    # groups 数组
    assert body.attrs["groups"].kind == "array"
    assert len(body.attrs["groups"].items) == 2

    # 嵌套属性名
    prop_names = [k for s in doc.sections for k, _ in s.props]
    assert "custom_colors/font_color" in prop_names

    # 转义引号
    text_prop = next(v for k, v in _props_of(doc, "Body") if k == "text")
    assert text_prop.kind == "str"
    assert '\\"' in text_prop.raw

    # 空 NodePath("")
    empty = next(v for k, v in _props_of(doc, "Body") if k == "empty_path")
    assert empty.kind == "call"
    assert empty.name == "NodePath"
    assert empty.items[0].raw == '""'

    # 尾随逗号
    points = next(v for k, v in _props_of(doc, "Body") if k == "points")
    assert points.kind == "call"
    assert points.name == "PoolVector2Array"
    assert points.raw.rstrip().endswith(")")

    # instance_placeholder
    ph = next(s for s in doc.sections if s.attrs.get("name", Value("str", "", None)).raw == '"Placeholder"')
    assert "instance_placeholder" in ph.attrs

    # CRLF 与无尾换行不抛异常（能跑到这里就成立）
    assert "\r\n" in text
    assert not text.endswith("\n")


def _props_of(doc, node_name: str):
    for s in doc.sections:
        if s.kind == "node" and s.attrs.get("name", Value("str", "", None)).raw == f'"{node_name}"':
            yield from s.props


# ---------------------------------------------------------------------------
# 验收 5：格式矩阵——godot4 generated
# ---------------------------------------------------------------------------


def test_godot4_matrix() -> None:
    text = _read_raw(GODOT4_MATRIX)
    doc = parse_scene(text, str(GODOT4_MATRIX))
    assert doc.problems == [], f"problems: {[(p.code, p.message) for p in doc.problems]}"
    assert doc.format == 3
    assert doc.uid == "uid://cecaux1sm7mo0"

    # 外部编号与内部编号同为 1_7bt6s 不算重复 id（分表，不合并）
    ext = next(s for s in doc.sections if s.kind == "ext_resource")
    sub = next(s for s in doc.sections if s.kind == "sub_resource")
    assert ext.attrs["id"].raw == '"1_7bt6s"'
    assert sub.attrs["id"].raw == '"1_7bt6s"'

    # 字符串 id
    assert ext.attrs["id"].kind == "str"

    # Array[Node]([])
    mesh_node = next(
        s for s in doc.sections
        if s.kind == "node" and s.attrs.get("name", Value("str", "", None)).raw == '"MeshInstance3D"'
    )
    nodes_prop = next(v for k, v in mesh_node.props if k == "nodes")
    assert nodes_prop.kind == "typed_array"
    assert nodes_prop.name == "Array[Node]"
    # Array[Node]([])：items 里是内层那个空 array
    assert len(nodes_prop.items) == 1
    assert nodes_prop.items[0].kind == "array"
    assert nodes_prop.items[0].items == []

    # libraries/""
    lib_prop = next((k, v) for k, v in mesh_node.props if k == 'libraries/""')
    assert lib_prop[1].kind == "call"
    assert lib_prop[1].name == "ExtResource"

    # theme_override_colors/font_color
    theme_prop = next((k, v) for k, v in mesh_node.props if k == "theme_override_colors/font_color")
    assert theme_prop[1].kind == "call"
    assert theme_prop[1].name == "Color"

    # Transform3D
    cam = next(
        s for s in doc.sections
        if s.kind == "node" and s.attrs.get("name", Value("str", "", None)).raw == '"Camera3D"'
    )
    tf = next(v for k, v in cam.props if k == "transform")
    assert tf.kind == "call"
    assert tf.name == "Transform3D"
    assert len(tf.items) == 12

    # binds= [（等号后有空格）
    conn = next(s for s in doc.sections if s.kind == "connection")
    assert "binds" in conn.attrs
    assert conn.attrs["binds"].kind == "array"

    # node_paths
    omni = next(
        s for s in doc.sections
        if s.kind == "node" and s.attrs.get("name", Value("str", "", None)).raw == '"OmniLight3D"'
    )
    assert "node_paths" in omni.attrs
    assert omni.attrs["node_paths"].kind == "call"
    assert omni.attrs["node_paths"].name == "PackedStringArray"

    # CRLF 与无尾换行
    assert "\r\n" in text
    assert not text.endswith("\n")


def test_godot4_strname() -> None:
    """&"..." 在 real_dodge_player 里。"""
    path = FIXTURE_ROOT / "godot4" / "real_dodge_player.tscn"
    text = _read_raw(path)
    doc = parse_scene(text, str(path))
    assert doc.problems == []
    # animation = &"right"
    anim = next(
        v for s in doc.sections for k, v in s.props if k == "animation"
    )
    assert anim.kind == "strname"
    assert anim.raw == '&"right"'


# ---------------------------------------------------------------------------
# 验收 6：随机截断 / 字节翻转不抛异常
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ALL_TSCN, ids=lambda p: p.name)
def test_random_truncation_no_crash(path: Path) -> None:
    text = _read_raw(path)
    rng = random.Random(42)
    for _ in range(20):
        cut = rng.randint(1, len(text))
        doc = parse_scene(text[:cut], str(path))
        assert isinstance(doc.problems, list)


@pytest.mark.parametrize("path", ALL_TSCN, ids=lambda p: p.name)
def test_random_byte_flip_no_crash(path: Path) -> None:
    text = _read_raw(path)
    rng = random.Random(42)
    for _ in range(20):
        pos = rng.randint(0, len(text) - 1)
        mutated = text[:pos] + chr(rng.randint(32, 126)) + text[pos + 1 :]
        doc = parse_scene(mutated, str(path))
        assert isinstance(doc.problems, list)


# ---------------------------------------------------------------------------
# 验收 7：每个 P_* 至少 1 个正例 + 1 个易混淆反例
# ---------------------------------------------------------------------------


class TestUnterminatedString:
    def test_positive(self) -> None:
        doc = parse_scene('[gd_scene format=3]\n\n[node name="A" type="Node"]\ntext = "hello\n')
        codes = [p.code for p in doc.problems]
        assert "P_UNTERMINATED_STRING" in codes

    def test_negative_escaped_quote(self) -> None:
        doc = parse_scene('[gd_scene format=3]\n\n[node name="A" type="Node"]\ntext = "say \\"hi\\""\n')
        codes = [p.code for p in doc.problems]
        assert "P_UNTERMINATED_STRING" not in codes


class TestUnbalancedBracket:
    def test_positive_call(self) -> None:
        doc = parse_scene('[gd_scene format=3]\n\n[node name="A" type="Node"]\npos = Vector2(1, 2\n')
        codes = [p.code for p in doc.problems]
        assert "P_UNBALANCED_BRACKET" in codes

    def test_positive_array(self) -> None:
        doc = parse_scene('[gd_scene format=3]\n\n[node name="A" type="Node"]\nx = [1, 2\n')
        codes = [p.code for p in doc.problems]
        assert "P_UNBALANCED_BRACKET" in codes

    def test_negative_parens_in_string(self) -> None:
        doc = parse_scene('[gd_scene format=3]\n\n[node name="A" type="Node"]\ntext = "((("\n')
        codes = [p.code for p in doc.problems]
        assert "P_UNBALANCED_BRACKET" not in codes


class TestMalformedHeading:
    def test_positive(self) -> None:
        doc = parse_scene('[gd_scene format=3]\n[node = bad]\n')
        codes = [p.code for p in doc.problems]
        assert "P_MALFORMED_HEADING" in codes

    def test_negative_array_value(self) -> None:
        """[1, 2] 是数组值，不是 section 头。"""
        doc = parse_scene('[gd_scene format=3]\n\n[node name="A" type="Node"]\nx = [1, 2]\n')
        codes = [p.code for p in doc.problems]
        assert "P_MALFORMED_HEADING" not in codes


class TestMissingFileDescriptor:
    def test_positive_garbage_first(self) -> None:
        doc = parse_scene('hello world\n[gd_scene format=3]\n')
        codes = [p.code for p in doc.problems]
        assert "P_MISSING_FILE_DESCRIPTOR" in codes

    def test_positive_wrong_first_section(self) -> None:
        doc = parse_scene('[node name="A" type="Node"]\n')
        codes = [p.code for p in doc.problems]
        assert "P_MISSING_FILE_DESCRIPTOR" in codes

    def test_negative_gd_resource(self) -> None:
        doc = parse_scene('[gd_resource type="StyleBoxFlat" format=3]\n')
        codes = [p.code for p in doc.problems]
        assert "P_MISSING_FILE_DESCRIPTOR" not in codes
        assert doc.doc_kind == "resource"


class TestPropBeforeSection:
    def test_positive(self) -> None:
        doc = parse_scene('[gd_scene format=3]\nkey = 1\n')
        # key=1 在 gd_scene 之后，不属于 PROP_BEFORE_SECTION
        # 需要一个在首个 section 之前的 prop
        doc2 = parse_scene('key = 1\n[gd_scene format=3]\n')
        codes = [p.code for p in doc2.problems]
        assert "P_PROP_BEFORE_SECTION" in codes

    def test_negative_prop_inside_section(self) -> None:
        doc = parse_scene('[gd_scene format=3]\n\n[node name="A" type="Node"]\nz_index = 10\n')
        codes = [p.code for p in doc.problems]
        assert "P_PROP_BEFORE_SECTION" not in codes


class TestGitConflictMarker:
    def test_positive(self) -> None:
        doc = parse_scene('[gd_scene format=3]\n<<<<<<< HEAD\nx = 1\n=======\nx = 2\n>>>>>>> branch\n')
        codes = [p.code for p in doc.problems]
        assert "P_GIT_CONFLICT_MARKER" in codes

    def test_negative_angle_in_string(self) -> None:
        doc = parse_scene('[gd_scene format=3]\n\n[node name="A" type="Node"]\ntext = "a <<< b"\n')
        codes = [p.code for p in doc.problems]
        assert "P_GIT_CONFLICT_MARKER" not in codes


class TestUnknownSection:
    def test_positive(self) -> None:
        doc = parse_scene('[gd_scene format=3]\n\n[future_section foo=1]\n')
        codes = [p.code for p in doc.problems]
        assert "W_UNKNOWN_SECTION" in codes

    def test_negative_known_sections(self) -> None:
        doc = parse_scene('[gd_scene format=3]\n\n[ext_resource path="res://a.gd" type="Script" id="1"]\n\n[node name="A" type="Node"]\n\n[connection signal="x" from="." to="." method="y"]\n')
        codes = [p.code for p in doc.problems]
        assert "W_UNKNOWN_SECTION" not in codes


# ---------------------------------------------------------------------------
# 验收 8：PoolByteArray(...) / NotARealType(...) 保留为 call，不报语法错误
# ---------------------------------------------------------------------------


def test_unknown_call_preserved() -> None:
    doc = parse_scene(
        '[gd_scene format=3]\n\n[node name="A" type="Node"]\n'
        'data = PoolByteArray(1, 2, 3)\n'
        'thing = NotARealType("x", 42)\n'
    )
    assert doc.problems == []
    props = dict(doc.sections[-1].props)
    assert props["data"].kind == "call"
    assert props["data"].name == "PoolByteArray"
    assert len(props["data"].items) == 3
    assert props["thing"].kind == "call"
    assert props["thing"].name == "NotARealType"
    assert len(props["thing"].items) == 2


# ---------------------------------------------------------------------------
# 补充：doc_kind / format / uid / script_class
# ---------------------------------------------------------------------------


def test_gd_resource_doc_kind() -> None:
    doc = parse_scene('[gd_resource type="StyleBoxFlat" script_class="MyStyle" format=3 uid="uid://abc"]\n')
    assert doc.doc_kind == "resource"
    assert doc.format == 3
    assert doc.uid == "uid://abc"
    assert doc.script_class == "MyStyle"


def test_empty_file() -> None:
    doc = parse_scene("")
    codes = [p.code for p in doc.problems]
    assert "P_MISSING_FILE_DESCRIPTOR" in codes


def test_comment_only_file() -> None:
    doc = parse_scene("; just a comment\n")
    codes = [p.code for p in doc.problems]
    assert "P_MISSING_FILE_DESCRIPTOR" in codes
