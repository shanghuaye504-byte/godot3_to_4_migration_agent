"""`rules/protect.py` 的纯函数测试（方案文档 §7.1）。

覆盖要点：
- `Parse Error: Class "…" hides an autoload singleton.`（样例 B）→ `role="protected"`。
- `Parse Error: Identifier "…" not declared in the current scope.`（样例 H）→ `role="protected"`。
- 任意 `kind="parse_error"` 且不是 pointer 三种文案（样例 E）→ `role="protected"`。
- `SHADER ERROR:` 前缀（样例 J）→ `role="protected"`。
- pointer 事件（样例 F，kind 同样是 parse_error）**不得**被误标为 protected。
- `Compile Error: Identifier not found: X`（样例 A/D）**不在**保护名单，`role` 不受影响。
"""

from __future__ import annotations

from godot_mcp.verify_filter.parse import classify, parse_raw_events
from godot_mcp.verify_filter.rules.protect import mark_protected


def test_sample_b_hides_autoload_becomes_protected(load_fixture):
    events = mark_protected(classify(parse_raw_events("", load_fixture("sample_b_autoload_shadow_real.log"))))
    assert events[0].role == "protected"


def test_sample_h_not_declared_becomes_protected(load_fixture):
    events = mark_protected(classify(parse_raw_events("", load_fixture("sample_h_cold_class_name.log"))))
    assert events[0].role == "protected"


def test_sample_e_generic_parse_error_becomes_protected(load_fixture):
    events = mark_protected(classify(parse_raw_events("", load_fixture("sample_e_real_syntax_error.log"))))
    assert events[0].role == "protected"


def test_sample_j_shader_error_becomes_protected(load_fixture):
    events = mark_protected(classify(parse_raw_events("", load_fixture("sample_j_shader_error.log"))))
    assert events[0].role == "protected"
    assert events[0].prefix == "SHADER ERROR"


def test_sample_f_pointer_not_marked_protected(load_fixture):
    events = mark_protected(classify(parse_raw_events("", load_fixture("sample_f_pointer_dep1.log"))))
    assert events[0].role == "pointer"
    assert events[1].role == "pointer"


def test_sample_a_identifier_not_found_untouched(load_fixture):
    events = mark_protected(classify(parse_raw_events("", load_fixture("sample_a_autoload_fp_cold.log"))))
    assert events[0].kind == "compile_error"
    assert events[0].role == "root_cause"  # 不在保护名单，留给 R2 判断
