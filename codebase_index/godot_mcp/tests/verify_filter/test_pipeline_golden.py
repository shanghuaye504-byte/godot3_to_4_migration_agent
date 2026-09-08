"""端到端流水线回归测试 —— 方案文档 §10 的完整测试矩阵。喂 `filter_verify_output` 完整输入，

断言最终 `FilterResult` 的 `root_cause_errors`/`dropped`/`untrusted_files`/`pointers`。
这是"完成定义"（§14）第 1 条要求的"§10 全部黄金测试绿"。

| ID | 输入 | autoload_keys | 断言 |
| --- | --- | --- | --- |
| T-A | 样例 A | `{Config}` | 0 条 root_cause；1 条 FP drop；`uses_autoload.gd` ∈ untrusted；包装行 dropped |
| T-A2 | 样例 A | `{}` | 1 条 root_cause（Identifier not found: Config），**不删** |
| T-B | 样例 B | `{Config}` | 1 条 root_cause（hides an autoload）；0 条 FP drop |
| T-C | 样例 C | `{Config}` | 0 条 root_cause；两条 FP；哨兵 depended + Failed to load 均 drop |
| T-D | 样例 D | `{DummySingleton}` | 与 T-A 同构 |
| T-E | 样例 E | 任意 | 1 条 parse root_cause；包装 symptom |
| T-F | 样例 F | 任意 | `status=CLEAN`；1 条 pointer，`target_res_path=res://root_bad.gd`，`res_path=res://dep_1.gd`；无 Unexpected Indent |
| T-G | 样例 G | 任意 | pointer 同 T-F；depended scripts 为 symptom；leaf 包装 drop |
| T-H | 样例 H | `{ProbeFoo}` 或 `{}` | **都必须留下** Parse Error not declared；不得当 FP |
| T-I | 样例 I | 任意 | 恰好 1 条 UID duplicate root_cause；Busy/Failed loading 为 cluster；debugger 行 drop |
| T-J | 样例 J | 任意 | 1 条 SHADER ERROR root_cause；`Shader compilation failed` 为包装 symptom |
| T-MIX | 同一 stderr：Config FP + Unexpected Indent（不同文件） | `{Config}` | Indent 必须留下 |
| T-STOP | 文档化用例：仅 Config FP，无其它行 | `{Config}` | status=CLEAN 且 untrusted 非空 |

"完成定义"（§14）还要求额外核对：
- 任意一条 `protected` 文案在带齐全白名单时仍出现在 `root_cause_errors`（§14 第 2 条）。
- 样例 C 过滤后 `root_cause_errors` 为空，且 `untrusted_files` 含 `main.gd` 与
  `uses_autoload.gd`（§14 第 3 条）。
- 样例 A 包装行是 dropped，不是 root_cause（R4 不得因 R2 升级，§14 第 5 条）。
"""

from __future__ import annotations

from godot_mcp.verify_filter.pipeline import filter_verify_output


def test_t_a_sample_a_config_whitelisted(load_fixture):
    stderr = load_fixture("sample_a_autoload_fp_cold.log")
    result = filter_verify_output("", stderr, command="V2", autoload_keys=frozenset({"Config"}))

    assert result.status == "CLEAN"
    assert result.root_cause_errors == []
    assert len(result.dropped) == 1  # FP
    assert len(result.symptoms) == 1  # 包装行（symptom 桶，供 LLM 参考，不是 root_cause）
    assert result.untrusted_files == frozenset({"res://uses_autoload.gd"})
    assert result.caveats == ["compile_truncated:res://uses_autoload.gd"]

    fp = [e for e in result.dropped if e.drop_reason == "autoload_identifier_fp"]
    wrapper = [e for e in result.symptoms if e.drop_reason == "failed_to_load_wrapper"]
    assert len(fp) == 1
    assert len(wrapper) == 1  # §14 第 5 条：包装行不是 root_cause（未因 R2 被升级）


def test_t_a2_sample_a_without_whitelist(load_fixture):
    stderr = load_fixture("sample_a_autoload_fp_cold.log")
    result = filter_verify_output("", stderr, command="V2", autoload_keys=frozenset())

    assert result.status == "HAS_ERRORS"
    assert len(result.root_cause_errors) == 1
    assert result.root_cause_errors[0].message == "Compile Error: Identifier not found: Config"


def test_t_b_sample_b_real_conflict_kept(load_fixture):
    stderr = load_fixture("sample_b_autoload_shadow_real.log")
    result = filter_verify_output("", stderr, command="V2", autoload_keys=frozenset({"Config"}))

    assert result.status == "HAS_ERRORS"
    assert len(result.root_cause_errors) == 1
    assert "hides an autoload singleton" in result.root_cause_errors[0].message
    assert result.dropped == []


def test_t_c_sample_c_project_amplified_fp_and_sentinel_symptoms(load_fixture):
    stderr = load_fixture("sample_c_autoload_v1_amplified.log")
    result = filter_verify_output("", stderr, command="V1", autoload_keys=frozenset({"Config"}))

    assert result.status == "CLEAN"
    assert result.root_cause_errors == []
    assert result.untrusted_files == frozenset({"res://main.gd", "res://uses_autoload.gd"})

    fp_events = [e for e in result.dropped if e.drop_reason == "autoload_identifier_fp"]
    sentinel_events = [e for e in result.dropped if e.drop_reason == "sentinel_artifact"]
    assert len(fp_events) == 2
    assert len(sentinel_events) == 2  # depended scripts + wrapper，都挂在哨兵上


def test_t_d_sample_d_addon_singleton_same_as_t_a(load_fixture):
    stderr = load_fixture("sample_d_addon_singleton_fp.log")
    result = filter_verify_output("", stderr, command="V2", autoload_keys=frozenset({"DummySingleton"}))

    assert result.status == "CLEAN"
    assert result.root_cause_errors == []
    assert result.untrusted_files == frozenset({"res://uses_addon.gd"})


def test_t_e_sample_e_real_syntax_error(load_fixture):
    stderr = load_fixture("sample_e_real_syntax_error.log")
    result = filter_verify_output("", stderr, command="V2", autoload_keys=frozenset())

    assert result.status == "HAS_ERRORS"
    assert len(result.root_cause_errors) == 1
    assert result.root_cause_errors[0].message == "Parse Error: Expected parameter name."

    wrapper_symptoms = [e for e in result.symptoms if e.drop_reason == "failed_to_load_wrapper"]
    assert len(wrapper_symptoms) == 1


def test_t_f_sample_f_pointer_clean_but_not_complete(load_fixture):
    stderr = load_fixture("sample_f_pointer_dep1.log")
    result = filter_verify_output("", stderr, command="V2", autoload_keys=frozenset())

    assert result.status == "CLEAN"  # 单次 CLEAN，但项目级并未完成（那是 merge.py 的判断）
    assert len(result.pointers) == 1
    assert result.pointers[0].target_res_path == "res://root_bad.gd"
    assert result.pointers[0].res_path == "res://dep_1.gd"
    assert all("Unexpected" not in e.message for e in result.root_cause_errors + result.symptoms + result.dropped)


def test_t_g_sample_g_pointer_plus_depended_scripts_symptom(load_fixture):
    stderr = load_fixture("sample_g_pointer_leaf_cascade.log")
    result = filter_verify_output("", stderr, command="V2", autoload_keys=frozenset())

    assert len(result.pointers) == 1
    assert result.pointers[0].target_res_path == "res://root_bad.gd"

    depended = [e for e in result.symptoms if e.drop_reason == "depended_scripts_compile"]
    assert len(depended) == 1
    wrapper = [e for e in result.symptoms if e.drop_reason == "failed_to_load_wrapper"]
    assert len(wrapper) == 1


def test_t_h_not_declared_survives_with_or_without_whitelist(load_fixture):
    stderr = load_fixture("sample_h_cold_class_name.log")

    for autoload_keys in (frozenset({"ProbeFoo"}), frozenset()):
        result = filter_verify_output("", stderr, command="V2", autoload_keys=autoload_keys)
        assert result.status == "HAS_ERRORS"
        assert len(result.root_cause_errors) == 1
        assert "not declared in the current scope" in result.root_cause_errors[0].message


def test_t_i_sample_i_uid_cluster(load_fixture):
    stderr = load_fixture("sample_i_uid_duplicate_cluster.log")
    result = filter_verify_output("", stderr, command="V3", autoload_keys=frozenset())

    assert result.status == "HAS_ERRORS"
    assert len(result.root_cause_errors) == 1
    assert "UID duplicate detected" in result.root_cause_errors[0].message

    debugger_dropped = [e for e in result.dropped if e.drop_reason == "debugger_plugin_detached"]
    assert len(debugger_dropped) == 1
    cluster_dropped = [e for e in result.dropped if e.drop_reason == "uid_duplicate_satellite"]
    assert len(cluster_dropped) == 4


def test_t_j_sample_j_shader_root_cause_and_wrapper_symptom(load_fixture):
    stderr = load_fixture("sample_j_shader_error.log")
    result = filter_verify_output("", stderr, command="V3", autoload_keys=frozenset())

    assert result.status == "HAS_ERRORS"
    assert len(result.root_cause_errors) == 1
    assert result.root_cause_errors[0].kind == "shader_error"
    assert result.root_cause_errors[0].role == "protected"

    shader_wrapper = [e for e in result.symptoms if "Shader compilation failed" in e.message]
    assert len(shader_wrapper) == 1


def test_t_mix_config_fp_and_indent_error_in_same_stream():
    stderr = (
        'SCRIPT ERROR: Compile Error: Identifier not found: Config\n'
        "          at: GDScript::reload (res://uses_autoload.gd:4)\n"
        'ERROR: Failed to load script "res://uses_autoload.gd" with error "Compilation failed".\n'
        "   at: load (modules/gdscript/gdscript_resource_format.cpp:46)\n"
        'SCRIPT ERROR: Parse Error: Unexpected "Indent" in class body.\n'
        "          at: GDScript::reload (res://scene_bad.gd:4)\n"
        'ERROR: Failed to load script "res://scene_bad.gd" with error "Parse error".\n'
        "   at: load (modules/gdscript/gdscript_resource_format.cpp:46)\n"
    )
    result = filter_verify_output("", stderr, command="V1", autoload_keys=frozenset({"Config"}))

    assert len(result.root_cause_errors) == 1
    assert "Unexpected" in result.root_cause_errors[0].message
    assert all(e.res_path != "res://scene_bad.gd" for e in result.dropped)


def test_t_stop_only_fp_no_other_lines(load_fixture):
    stderr = load_fixture("sample_a_autoload_fp_cold.log")
    result = filter_verify_output("", stderr, command="V2", autoload_keys=frozenset({"Config"}))

    assert result.status == "CLEAN"
    assert result.untrusted_files != frozenset()  # 表面干净，不代表确认干净


def test_no_exit_code_shortcut_exists_in_module_source():
    """§14 第 7 条（代码审查项）：过滤器内部不应该出现 `exit_code` 相关的短路判断。"""
    import inspect

    from godot_mcp.verify_filter import pipeline

    source = inspect.getsource(pipeline)
    assert "exit_code" not in source
