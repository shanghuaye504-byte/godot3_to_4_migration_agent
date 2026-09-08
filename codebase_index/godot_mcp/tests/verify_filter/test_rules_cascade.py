"""`rules/cascade.py` 的纯函数测试（方案文档 §7.4）。对应 §10 的 T-G 的 depended-scripts 部分。

覆盖要点：
- 样例 G（二级依赖 + depended scripts）：`Compile Error: Failed to compile depended
  scripts.` → `role="symptom"`，`drop_reason="depended_scripts_compile"`。
- 样例 F（一级依赖，没有这条症状行）：本规则在这份样例上是无操作。
- 已经被 R1 消化成 `false_positive`（哨兵）的事件：本规则 skip，不重复改写。
"""

from __future__ import annotations

from godot_mcp.verify_filter.parse import classify, parse_raw_events
from godot_mcp.verify_filter.rules.cascade import apply_cascade_symptom_rule
from godot_mcp.verify_filter.rules.sentinel import apply_sentinel_rule


def test_sample_g_depended_scripts_becomes_symptom(load_fixture):
    classified = classify(parse_raw_events("", load_fixture("sample_g_pointer_leaf_cascade.log")))
    result = apply_cascade_symptom_rule(classified)

    depended = [e for e in result if "depended scripts" in e.message]
    assert len(depended) == 1
    assert depended[0].role == "symptom"
    assert depended[0].drop_reason == "depended_scripts_compile"


def test_sample_f_no_depended_scripts_line_is_noop(load_fixture):
    classified = classify(parse_raw_events("", load_fixture("sample_f_pointer_dep1.log")))
    result = apply_cascade_symptom_rule(classified)
    assert [e.role for e in result] == [e.role for e in classified]


def test_sentinel_dropped_depended_scripts_not_reprocessed(load_fixture):
    classified = classify(parse_raw_events("", load_fixture("sample_c_autoload_v1_amplified.log")))
    after_sentinel = apply_sentinel_rule(classified, sentinel_res_paths=frozenset({"res://__probe_sentinel.gd"}))
    after_cascade = apply_cascade_symptom_rule(after_sentinel)

    sentinel_depended = [e for e in after_cascade if e.res_path == "res://__probe_sentinel.gd"]
    for e in sentinel_depended:
        assert e.role == "false_positive"
        assert e.drop_reason == "sentinel_artifact"  # 没有被 R3 改成 depended_scripts_compile
