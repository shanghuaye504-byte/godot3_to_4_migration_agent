"""`rules/wrappers.py` 的纯函数测试（方案文档 §7.5，含窄"升级例外"）。

覆盖要点：
- 样例 A（经 R2 过滤后）：`Failed to load script "res://uses_autoload.gd" ...` 必须是
  `role="symptom"`，`drop_reason="failed_to_load_wrapper"`，**禁止**因为对应的
  SCRIPT ERROR 被 R2 删掉而升级成 `root_cause`（T-A 的关键断言）。
- 样例 E（真语法错误）：SCRIPT ERROR 保留，包装行仍降级为 symptom。
- 升级例外（合成样例，4.7.1 探针未观测到）：构造一份"该 `res_path` 在原始解析结果里
  从未出现过任何 SCRIPT ERROR"的输入，断言包装行被升级为 `root_cause`。
- 反例：用"因 R2 被删空"的情况构造输入，断言**不**触发升级——必须用解析完成、过滤
  开始之前的快照判断，不能用过滤中途的集合代替。
"""

from __future__ import annotations

from godot_mcp.verify_filter.models import ClassifiedEvent
from godot_mcp.verify_filter.parse import classify, parse_raw_events
from godot_mcp.verify_filter.rules.autoload_fp import apply_autoload_fp_rule
from godot_mcp.verify_filter.rules.wrappers import apply_wrapper_rule


def _group_by_res_path(events: list[ClassifiedEvent]) -> dict[str, list[ClassifiedEvent]]:
    groups: dict[str, list[ClassifiedEvent]] = {}
    for e in events:
        if e.res_path:
            groups.setdefault(e.res_path, []).append(e)
    return groups


def test_t_a_wrapper_not_upgraded_after_r2_removes_script_error(load_fixture):
    stderr = load_fixture("sample_a_autoload_fp_cold.log")
    original = classify(parse_raw_events("", stderr))
    original_by_res_path = _group_by_res_path(original)  # R2 跑之前的快照

    after_r2, _untrusted, _caveats = apply_autoload_fp_rule(original, autoload_keys=frozenset({"Config"}))
    result = apply_wrapper_rule(after_r2, original_events_by_res_path=original_by_res_path)

    wrapper = [e for e in result if e.kind == "resource_error"][0]
    assert wrapper.role == "symptom"
    assert wrapper.drop_reason == "failed_to_load_wrapper"


def test_sample_e_wrapper_downgraded_symptom(load_fixture):
    stderr = load_fixture("sample_e_real_syntax_error.log")
    original = classify(parse_raw_events("", stderr))
    original_by_res_path = _group_by_res_path(original)
    result = apply_wrapper_rule(original, original_events_by_res_path=original_by_res_path)

    wrapper = [e for e in result if e.kind == "resource_error"][0]
    assert wrapper.role == "symptom"
    script_error = [e for e in result if e.prefix == "SCRIPT ERROR"][0]
    assert script_error.role == "root_cause"  # wrappers 规则不动 SCRIPT ERROR


def _wrapper_event(res_path: str) -> ClassifiedEvent:
    return ClassifiedEvent(
        prefix="ERROR",
        message=f'Failed to load script "{res_path}" with error "Parse error".',
        at_function="load",
        at_location="modules/gdscript/gdscript_resource_format.cpp:46",
        res_path=res_path,
        target_res_path=None,
        line_in_project=None,
        engine_location="modules/gdscript/gdscript_resource_format.cpp:46",
        source_stream="stderr",
        raw_block="",
        kind="resource_error",
        symbol=None,
        msg_template="x",
        local_signature="sig",
        noise_signature="noise",
        role="symptom",
    )


def test_upgrade_exception_when_no_script_error_ever_existed():
    wrapper = _wrapper_event("res://only_wrapper.gd")
    # original_events_by_res_path 里根本没有这个 res_path 的记录：从解析完成那一刻起
    # 就没有任何 SCRIPT ERROR。
    result = apply_wrapper_rule([wrapper], original_events_by_res_path={})
    assert result[0].role == "root_cause"
    assert result[0].drop_reason is None


def test_no_upgrade_when_script_error_existed_but_was_filtered_out_later():
    wrapper = _wrapper_event("res://had_script_error.gd")
    fake_original_script_error = ClassifiedEvent(
        prefix="SCRIPT ERROR",
        message="Compile Error: Identifier not found: Config",
        at_function="GDScript::reload",
        at_location="res://had_script_error.gd:4",
        res_path="res://had_script_error.gd",
        target_res_path=None,
        line_in_project=4,
        engine_location=None,
        source_stream="stderr",
        raw_block="",
        kind="compile_error",
        symbol="Config",
        msg_template="x",
        local_signature="sig2",
        noise_signature="noise2",
        role="false_positive",  # 已经被 R2 删掉，但它"曾经存在过"
    )
    original_by_res_path = {"res://had_script_error.gd": [fake_original_script_error]}
    result = apply_wrapper_rule([wrapper], original_events_by_res_path=original_by_res_path)
    assert result[0].role == "symptom"
    assert result[0].drop_reason == "failed_to_load_wrapper"


def test_false_positive_wrapper_from_sentinel_rule_untouched():
    wrapper = _wrapper_event("res://__probe_sentinel.gd")
    dropped = ClassifiedEvent(**{**wrapper.__dict__, "role": "false_positive", "drop_reason": "sentinel_artifact"})
    result = apply_wrapper_rule([dropped], original_events_by_res_path={})
    assert result[0].role == "false_positive"
    assert result[0].drop_reason == "sentinel_artifact"
