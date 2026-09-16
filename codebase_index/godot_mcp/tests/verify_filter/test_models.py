"""`models.py` 的最基础一层：dataclass 能 round-trip，`replace()` 能改 role。

方案文档 §3 实现顺序第 1 步的完成标准：models.py 能 round-trip；replace() 能改 role。
"""

from __future__ import annotations

from dataclasses import replace

from godot_mcp.verify_filter.models import (
    ClassifiedEvent,
    FilterResult,
    ProjectFilterView,
)


def _make_event(**overrides: object) -> ClassifiedEvent:
    base = dict(
        prefix="SCRIPT ERROR",
        message="Compile Error: Identifier not found: Config",
        at_function="GDScript::reload",
        at_location="res://uses_autoload.gd:4",
        res_path="res://uses_autoload.gd",
        target_res_path=None,
        line_in_project=4,
        engine_location=None,
        source_stream="stderr",
        raw_block="SCRIPT ERROR: Compile Error: Identifier not found: Config\n"
        "          at: GDScript::reload (res://uses_autoload.gd:4)",
        kind="compile_error",
        symbol="Config",
        local_signature="deadbeef",
    )
    base.update(overrides)
    return ClassifiedEvent(**base)  # type: ignore[arg-type]


def test_classified_event_round_trip():
    event = _make_event()
    assert event.prefix == "SCRIPT ERROR"
    assert event.symbol == "Config"
    assert event.role == "root_cause"  # dataclass 默认值
    assert event.drop_reason is None


def test_classified_event_replace_changes_role_without_mutating_original():
    original = _make_event()
    updated = replace(original, role="false_positive", drop_reason="autoload_identifier_fp")

    # 原对象不受影响（frozen + replace 的核心保证）
    assert original.role == "root_cause"
    assert original.drop_reason is None
    # 新对象拿到了改动
    assert updated.role == "false_positive"
    assert updated.drop_reason == "autoload_identifier_fp"
    # 其余字段原样保留
    assert updated.symbol == original.symbol
    assert updated.res_path == original.res_path


def test_classified_event_is_frozen():
    event = _make_event()
    try:
        event.role = "symptom"  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("ClassifiedEvent 应该是 frozen 的，直接赋值应该抛异常")


def test_filter_result_round_trip():
    event = _make_event()
    result = FilterResult(
        status="HAS_ERRORS",
        root_cause_errors=[event],
        pointers=[],
        symptoms=[],
        dropped=[],
        caveats=[],
        untrusted_files=frozenset(),
    )
    assert result.status == "HAS_ERRORS"
    assert result.root_cause_errors == [event]


def test_project_filter_view_round_trip():
    event = _make_event()
    view = ProjectFilterView(
        status="HAS_ERRORS",
        root_cause_errors=[event],
        pending_pointers=[],
        symptoms=[],
        dropped=[],
        caveats=["shader_not_checked"],
        untrusted_files=frozenset({"res://uses_autoload.gd"}),
        gdscript_complete=False,
        shader_checked=False,
    )
    assert view.gdscript_complete is False
    assert view.shader_checked is False
    assert "res://uses_autoload.gd" in view.untrusted_files
