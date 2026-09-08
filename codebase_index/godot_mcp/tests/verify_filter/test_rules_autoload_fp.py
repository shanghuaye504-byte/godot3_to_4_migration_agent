"""`rules/autoload_fp.py` 的纯函数测试（方案文档 §7.3，核心规则）。对应 §10 的 T-A/T-A2/T-D/T-MIX/T-STOP。

覆盖要点：
- T-A：样例 A + `autoload_keys={"Config"}` → 0 条 root_cause 候选（该事件被 drop）；
  1 条 FP drop（`drop_reason="autoload_identifier_fp"`）；`uses_autoload.gd` 进入
  `untrusted_files`。
- T-A2：样例 A + `autoload_keys={}`（空白名单）→ 事件不变，**不删**——白名单为空是
  合法状态，不能靠"看起来像 autoload 符号"猜测过滤。
- T-D：样例 D + `autoload_keys={"DummySingleton"}` → 与 T-A 同构（addon 单例复用
  同一条规则）。
- T-MIX：同一份事件列表里混合 Config FP（不同文件）与 `Unexpected Indent` 真错误 →
  Indent 那条必须留下，不受 Config 过滤影响。
- 不得删 `Parse Error: Identifier "X" not declared...`，即使 X 恰好等于某个 autoload key。
- 不得删 `Identifier not found: X` 当 X 不在 `autoload_keys` 里。
"""

from __future__ import annotations

from godot_mcp.verify_filter.parse import classify, parse_raw_events
from godot_mcp.verify_filter.rules.autoload_fp import apply_autoload_fp_rule


def test_t_a_sample_a_with_config_whitelist(load_fixture):
    classified = classify(parse_raw_events("", load_fixture("sample_a_autoload_fp_cold.log")))
    result, untrusted, caveats = apply_autoload_fp_rule(classified, autoload_keys=frozenset({"Config"}))

    fp_events = [e for e in result if e.role == "false_positive"]
    assert len(fp_events) == 1
    assert fp_events[0].drop_reason == "autoload_identifier_fp"
    assert untrusted == frozenset({"res://uses_autoload.gd"})
    assert caveats == ["compile_truncated:res://uses_autoload.gd"]


def test_t_a2_sample_a_with_empty_whitelist(load_fixture):
    classified = classify(parse_raw_events("", load_fixture("sample_a_autoload_fp_cold.log")))
    result, untrusted, caveats = apply_autoload_fp_rule(classified, autoload_keys=frozenset())

    assert all(e.role != "false_positive" for e in result)
    assert result[0].kind == "compile_error"
    assert result[0].role == "root_cause"
    assert untrusted == frozenset()
    assert caveats == []


def test_t_d_sample_d_with_dummy_singleton_whitelist(load_fixture):
    classified = classify(parse_raw_events("", load_fixture("sample_d_addon_singleton_fp.log")))
    result, untrusted, caveats = apply_autoload_fp_rule(classified, autoload_keys=frozenset({"DummySingleton"}))

    fp_events = [e for e in result if e.role == "false_positive"]
    assert len(fp_events) == 1
    assert untrusted == frozenset({"res://uses_addon.gd"})


def test_t_mix_config_fp_does_not_affect_unrelated_indent_error():
    from godot_mcp.verify_filter.models import ClassifiedEvent

    config_fp = ClassifiedEvent(
        prefix="SCRIPT ERROR",
        message="Compile Error: Identifier not found: Config",
        at_function="GDScript::reload",
        at_location="res://uses_autoload.gd:4",
        res_path="res://uses_autoload.gd",
        target_res_path=None,
        line_in_project=4,
        engine_location=None,
        source_stream="stderr",
        raw_block="",
        kind="compile_error",
        symbol="Config",
        msg_template="x",
        local_signature="sig-config-fp",
        noise_signature="noise-config-fp",
        role="root_cause",
    )
    indent_error = ClassifiedEvent(
        prefix="SCRIPT ERROR",
        message='Parse Error: Unexpected "Indent" in class body.',
        at_function="GDScript::reload",
        at_location="res://scene_bad.gd:4",
        res_path="res://scene_bad.gd",
        target_res_path=None,
        line_in_project=4,
        engine_location=None,
        source_stream="stderr",
        raw_block="",
        kind="parse_error",
        symbol=None,
        msg_template="y",
        local_signature="sig-indent",
        noise_signature="noise-indent",
        role="protected",  # 已经被 rules/protect.py 处理过
    )
    result, _untrusted, _caveats = apply_autoload_fp_rule(
        [config_fp, indent_error], autoload_keys=frozenset({"Config"})
    )
    fp_events = [e for e in result if e.role == "false_positive"]
    protected_events = [e for e in result if e.role == "protected"]
    assert len(fp_events) == 1
    assert len(protected_events) == 1
    assert protected_events[0].message == indent_error.message


def test_does_not_delete_not_declared_even_if_symbol_matches_whitelist(load_fixture):
    classified = classify(parse_raw_events("", load_fixture("sample_h_cold_class_name.log")))
    # ProbeFoo 恰好在白名单里，也不能被 R2 删——kind 是 parse_error 不是 compile_error
    result, _untrusted, _caveats = apply_autoload_fp_rule(classified, autoload_keys=frozenset({"ProbeFoo"}))
    assert result[0].role == "root_cause"
    assert result[0].kind == "parse_error"


def test_does_not_delete_identifier_not_found_when_symbol_not_whitelisted(load_fixture):
    classified = classify(parse_raw_events("", load_fixture("sample_a_autoload_fp_cold.log")))
    result, _untrusted, _caveats = apply_autoload_fp_rule(classified, autoload_keys=frozenset({"SomethingElse"}))
    assert result[0].role == "root_cause"
