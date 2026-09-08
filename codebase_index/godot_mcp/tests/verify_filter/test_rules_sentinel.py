"""`rules/sentinel.py` 的纯函数测试（方案文档 §7.2）。

覆盖要点：
- 样例 C（V1 放大 + 哨兵症状）：`res_path` 为 `res://__probe_sentinel.gd` 的
  `Compile Error: Failed to compile depended scripts` → drop，`drop_reason="sentinel_artifact"`。
- 同样例中 `Failed to load script "res://__probe_sentinel.gd" ...` → drop，
  `drop_reason="sentinel_artifact"`。
- 非哨兵路径的事件（`main.gd`/`uses_autoload.gd` 的 Config FP）不受影响。
- 样例 F 的 pointer 事件（`target_res_path` 指向哨兵之外的目标）原样保留，不被误伤。
- `sentinel_res_paths` 参数化：默认集合之外的自定义路径也能生效。
"""

from __future__ import annotations

from godot_mcp.verify_filter.parse import classify, parse_raw_events
from godot_mcp.verify_filter.rules.sentinel import apply_sentinel_rule

_DEFAULT_SENTINELS = frozenset({"res://__probe_sentinel.gd"})


def test_sample_c_sentinel_depended_scripts_and_wrapper_dropped(load_fixture):
    stderr = load_fixture("sample_c_autoload_v1_amplified.log")
    classified = classify(parse_raw_events("", stderr))
    result = apply_sentinel_rule(classified, sentinel_res_paths=_DEFAULT_SENTINELS)

    by_res_path = {(e.res_path, e.kind): e for e in result}

    sentinel_depended = by_res_path[("res://__probe_sentinel.gd", "compile_error")]
    assert sentinel_depended.role == "false_positive"
    assert sentinel_depended.drop_reason == "sentinel_artifact"

    sentinel_wrapper = by_res_path[("res://__probe_sentinel.gd", "resource_error")]
    assert sentinel_wrapper.role == "false_positive"
    assert sentinel_wrapper.drop_reason == "sentinel_artifact"

    main_fp = by_res_path[("res://main.gd", "compile_error")]
    assert main_fp.role == "root_cause"
    assert main_fp.drop_reason is None

    uses_autoload_fp = by_res_path[("res://uses_autoload.gd", "compile_error")]
    assert uses_autoload_fp.role == "root_cause"


def test_sample_f_pointer_untouched_by_sentinel_rule(load_fixture):
    stderr = load_fixture("sample_f_pointer_dep1.log")
    classified = classify(parse_raw_events("", stderr))
    result = apply_sentinel_rule(classified, sentinel_res_paths=_DEFAULT_SENTINELS)

    pointer_events = [e for e in result if e.role == "pointer"]
    assert len(pointer_events) == 2
    for e in pointer_events:
        assert e.target_res_path == "res://root_bad.gd"


def test_custom_sentinel_res_paths():
    from godot_mcp.verify_filter.models import ClassifiedEvent

    event = ClassifiedEvent(
        prefix="ERROR",
        message='Failed to load script "res://custom_sentinel.gd" with error "Compilation failed".',
        at_function="load",
        at_location="modules/gdscript/gdscript_resource_format.cpp:46",
        res_path="res://custom_sentinel.gd",
        target_res_path=None,
        line_in_project=None,
        engine_location="modules/gdscript/gdscript_resource_format.cpp:46",
        source_stream="stderr",
        raw_block="",
        kind="resource_error",
        symbol=None,
        msg_template="x",
        local_signature="a",
        noise_signature="b",
        role="symptom",
    )
    result = apply_sentinel_rule([event], sentinel_res_paths=frozenset({"res://custom_sentinel.gd"}))
    assert result[0].role == "false_positive"
    assert result[0].drop_reason == "sentinel_artifact"
