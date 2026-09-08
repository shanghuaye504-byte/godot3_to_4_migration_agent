"""`parse.py` 的纯函数测试：喂原始 stdout/stderr 样例，断言切出的 `RawEvent`/`ClassifiedEvent`。

覆盖要点（方案文档 §5、§10 的 T-A…T-J 对应输入）：
- §5.3 的十份黄金原文（A–J，见 `fixtures/godot_4_7_1/`）都能被 `parse_raw_events` 正确
  切成事件，字段（prefix/message/at_function/at_location/res_path/target_res_path/
  engine_location）逐一核对。
- 匹配优先级 `AT_SCRIPT → AT_ENGINE → AT_SHADER → AT_GENERIC`。
- `res_path` 与 `target_res_path` 的区分（样例 F）：`target_res_path == "res://root_bad.gd"`，
  `res_path == "res://dep_1.gd"`，两者不能互换。
- §5.4 明确不解析进事件的内容：空 stderr 产出零事件而不是抛异常。
- `classify()` 对 §5.2 表格里每一行文案给出正确的默认 `kind`/`symbol`/`role`。
"""

from __future__ import annotations

from godot_mcp.verify_filter.parse import classify, parse_raw_events


def test_empty_streams_produce_zero_events():
    assert parse_raw_events("", "") == []


def test_banner_and_print_lines_are_not_events():
    stdout = "Godot Engine v4.7.1.stable.official.a13da4feb - https://godotengine.org\nCONFIG_ALIVE\n"
    assert parse_raw_events(stdout, "") == []


def test_sample_a_autoload_fp_fields(load_fixture):
    stderr = load_fixture("sample_a_autoload_fp_cold.log")
    raw = parse_raw_events("", stderr)
    assert len(raw) == 2

    identifier_event, wrapper_event = raw
    assert identifier_event.prefix == "SCRIPT ERROR"
    assert identifier_event.message == "Compile Error: Identifier not found: Config"
    assert identifier_event.at_function == "GDScript::reload"
    assert identifier_event.res_path == "res://uses_autoload.gd"
    assert identifier_event.line_in_project == 4
    assert identifier_event.target_res_path is None
    assert identifier_event.engine_location is None

    assert wrapper_event.prefix == "ERROR"
    assert wrapper_event.res_path == "res://uses_autoload.gd"
    assert wrapper_event.engine_location == "modules/gdscript/gdscript_resource_format.cpp:46"
    # ERROR 的引擎行号不进 line_in_project（只有 SCRIPT ERROR 指向项目脚本时才填）
    assert wrapper_event.line_in_project is None

    classified = classify(raw)
    assert classified[0].kind == "compile_error"
    assert classified[0].symbol == "Config"
    assert classified[0].role == "root_cause"  # 待 R2 判断是否 FP
    assert classified[1].kind == "resource_error"
    assert classified[1].role == "symptom"


def test_sample_b_autoload_shadow_classified_as_parse_error(load_fixture):
    # classify() 只判定 kind/symbol/中性默认 role；升级为 "protected" 是 §7.1
    # （rules/protect.py）的职责，不在这里判断——见 test_rules_protect.py。
    stderr = load_fixture("sample_b_autoload_shadow_real.log")
    classified = classify(parse_raw_events("", stderr))
    assert classified[0].kind == "parse_error"
    assert classified[0].symbol == "Config"
    assert classified[0].role == "root_cause"


def test_sample_f_pointer_res_path_vs_target_res_path(load_fixture):
    stderr = load_fixture("sample_f_pointer_dep1.log")
    raw = parse_raw_events("", stderr)
    assert len(raw) == 3

    preload_event, resolve_event, wrapper_event = raw
    assert preload_event.target_res_path == "res://root_bad.gd"
    assert preload_event.res_path == "res://dep_1.gd"
    assert resolve_event.target_res_path == "res://root_bad.gd"
    assert resolve_event.res_path == "res://dep_1.gd"

    classified = classify(raw)
    assert classified[0].role == "pointer"
    assert classified[0].symbol == "res://root_bad.gd"  # pointer 的 symbol == target_res_path
    assert classified[1].role == "pointer"


def test_sample_g_depended_scripts_symptom(load_fixture):
    stderr = load_fixture("sample_g_pointer_leaf_cascade.log")
    classified = classify(parse_raw_events("", stderr))
    kinds_roles = [(e.kind, e.role) for e in classified]
    assert kinds_roles[0] == ("parse_error", "pointer")
    assert kinds_roles[1] == ("parse_error", "pointer")
    assert kinds_roles[2] == ("compile_error", "symptom")  # Failed to compile depended scripts
    assert kinds_roles[3] == ("resource_error", "symptom")  # Failed to load script wrapper


def test_sample_h_not_declared_classified_as_parse_error(load_fixture):
    # 同上：升级为 protected 是 rules/protect.py 的职责，见 test_rules_protect.py。
    stderr = load_fixture("sample_h_cold_class_name.log")
    classified = classify(parse_raw_events("", stderr))
    assert classified[0].kind == "parse_error"
    assert classified[0].symbol == "ProbeFoo"
    assert classified[0].role == "root_cause"


def test_sample_i_uid_cluster_raw_fields(load_fixture):
    stderr = load_fixture("sample_i_uid_duplicate_cluster.log")
    raw = parse_raw_events("", stderr)
    assert len(raw) == 6  # WARNING + 2×(Busy + Failed loading) + debugger plugin 行

    warning_event, busy1, failed1, busy2, failed2, _debugger_event = raw
    assert warning_event.prefix == "WARNING"
    assert warning_event.engine_location == "editor/file_system/editor_file_system.cpp:1405"
    assert busy1.res_path == "res://sub.tscn"
    assert failed1.res_path == "res://sub.tscn"
    assert busy2.res_path == "res://main.tscn"
    assert failed2.res_path == "res://main.tscn"

    classified = classify(raw)
    assert classified[0].kind == "warning"
    assert classified[1].kind == "resource_error"  # Busy
    assert classified[2].kind == "resource_error"  # Failed loading resource

    debugger_events = [e for e in classified if "Plugin is not attached" in e.message]
    assert len(debugger_events) == 1
    assert debugger_events[0].role == "infra_noise"


def test_sample_j_shader_error_fields(load_fixture):
    stderr = load_fixture("sample_j_shader_error.log")
    raw = parse_raw_events("", stderr)
    assert len(raw) == 2

    shader_event, wrapper_event = raw
    assert shader_event.prefix == "SHADER ERROR"
    assert shader_event.res_path is None  # shader 事件没有 res_path，用 (null)

    classified = classify(raw)
    assert classified[0].kind == "shader_error"
    assert classified[0].symbol == 'vec4(float,float,float)'
    assert classified[0].role == "root_cause"
    assert classified[1].kind == "shader_error"
    assert classified[1].role == "symptom"  # Shader compilation failed 包装
