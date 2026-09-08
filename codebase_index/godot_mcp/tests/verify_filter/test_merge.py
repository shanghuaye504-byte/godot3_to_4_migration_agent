"""`merge.py`（`merge_command_results`）的纯函数测试 —— 方案文档 §7.10/§7.10.1。

覆盖要点：
- 样例 F（单次 V2 CLEAN + pointer）：若对应 `target_res_path` 还没有 V2 结果，pointer
  必须**仍然**保留在 `pending_pointers` 里，不能被误判成"已经 drill-down 完成"。
- 若 `V2(target).root_cause_errors` 非空 → 丢弃指向该 target 的 pointer（根因已在 V2
  里，避免同一个问题在 `root_cause_errors` 和 `pending_pointers` 里各计一次）。
- 若 `V2(target)` 根因为空（只剩被滤掉的 FP）→ 丢弃 pointer，把 target 并入
  `untrusted_files`。
- 若某 pointer 还没有对应的 V2 结果 → `gdscript_complete=False`，即使 v1/所有已有
  V2 的 `status` 都是 `CLEAN`。
- 派生字段：`gdscript_complete`/`shader_checked`/`status` 的公式。
- `v3 is None` 时 `caveats` 含 `"shader_not_checked"`；`v3` 打出根因时这些根因必须
  并入 `root_cause_errors`。
- 多次调用契约：模拟两轮收敛过程，`v2_by_target` 累积增长。
"""

from __future__ import annotations

from godot_mcp.verify_filter.merge import merge_command_results
from godot_mcp.verify_filter.pipeline import filter_verify_output


def test_pointer_without_v2_stays_pending(load_fixture):
    v1 = filter_verify_output("", load_fixture("sample_f_pointer_dep1.log"), command="V1", autoload_keys=frozenset())
    view = merge_command_results(v1, {})

    assert len(view.pending_pointers) == 1
    assert view.pending_pointers[0].target_res_path == "res://root_bad.gd"
    assert view.gdscript_complete is False
    assert view.status == "CLEAN"  # v1 本身没有根因


def test_pointer_resolved_by_v2_with_real_root_cause(load_fixture):
    v1 = filter_verify_output("", load_fixture("sample_f_pointer_dep1.log"), command="V1", autoload_keys=frozenset())
    # 对 target（root_bad.gd）单独跑一次 V2，假设它本身就是缺冒号的语法错误
    v2_root_bad = filter_verify_output(
        "",
        'SCRIPT ERROR: Parse Error: Unexpected "Indent" in class body.\n'
        "          at: GDScript::reload (res://root_bad.gd:4)\n"
        'ERROR: Failed to load script "res://root_bad.gd" with error "Parse error".\n'
        "   at: load (modules/gdscript/gdscript_resource_format.cpp:46)\n",
        command="V2",
        autoload_keys=frozenset(),
    )
    view = merge_command_results(v1, {"res://root_bad.gd": v2_root_bad})

    assert view.pending_pointers == []  # pointer 已消化：根因已经出现在 root_cause_errors 里
    assert len(view.root_cause_errors) == 1
    assert "Unexpected" in view.root_cause_errors[0].message
    # 项目仍然没修完（root_bad.gd 真的有语法错误），gdscript_complete 必须是 False——
    # "pointer 已消化" 不等于 "项目已经干净"，这正是 gdscript_complete 公式里
    # "根因为空" 这一半条件存在的意义。
    assert view.gdscript_complete is False
    assert view.status == "HAS_ERRORS"


def test_pointer_resolved_by_v2_with_empty_result_marks_untrusted(load_fixture):
    v1 = filter_verify_output("", load_fixture("sample_f_pointer_dep1.log"), command="V1", autoload_keys=frozenset())
    # target 本身跑 V2 是 CLEAN（比如它其实没问题，级联链条本身有误报的可能）
    v2_clean = filter_verify_output("", "", command="V2", autoload_keys=frozenset())
    view = merge_command_results(v1, {"res://root_bad.gd": v2_clean})

    assert view.pending_pointers == []
    assert view.root_cause_errors == []
    assert "res://root_bad.gd" in view.untrusted_files
    assert view.gdscript_complete is True  # 根因空、pending 空——即便是靠 untrusted 兜底


def test_shader_not_checked_caveat_when_v3_absent(load_fixture):
    v1 = filter_verify_output("", load_fixture("sample_a_autoload_fp_cold.log"), command="V1", autoload_keys=frozenset({"Config"}))
    view = merge_command_results(v1, {})
    assert "shader_not_checked" in view.caveats
    assert view.shader_checked is False


def test_v3_root_causes_merged_and_shader_checked_true(load_fixture):
    v1 = filter_verify_output("", "", command="V1", autoload_keys=frozenset())
    v3 = filter_verify_output("", load_fixture("sample_j_shader_error.log"), command="V3", autoload_keys=frozenset())
    view = merge_command_results(v1, {}, v3=v3)

    assert view.shader_checked is True
    assert "shader_not_checked" not in view.caveats
    assert len(view.root_cause_errors) == 1
    assert view.root_cause_errors[0].kind == "shader_error"
    assert view.status == "HAS_ERRORS"


def test_multi_round_convergence_accumulates_v2_by_target(load_fixture):
    """模拟两轮收敛：第一轮只解出一个 target 且还有真错误，第二轮 target 已被 patch 修好，
    `v2_by_target` 累积增长，`gdscript_complete` 才从 False 变成 True——
    这条测试专门锁住"pointer 消化完 ≠ 项目完成"这个容易搞混的点。
    """
    v1 = filter_verify_output("", load_fixture("sample_g_pointer_leaf_cascade.log"), command="V1", autoload_keys=frozenset())

    # 第一轮：还没有任何 V2 结果，pointer 待消化
    view_round_1 = merge_command_results(v1, {})
    assert view_round_1.gdscript_complete is False
    assert len(view_round_1.pending_pointers) == 1

    # 第二轮：root_bad.gd 当时还有真错误，V2 消化出了根因，但项目还没修完
    v2_root_bad_broken = filter_verify_output(
        "",
        'SCRIPT ERROR: Parse Error: Unexpected "Indent" in class body.\n'
        "          at: GDScript::reload (res://root_bad.gd:4)\n"
        'ERROR: Failed to load script "res://root_bad.gd" with error "Parse error".\n'
        "   at: load (modules/gdscript/gdscript_resource_format.cpp:46)\n",
        command="V2",
        autoload_keys=frozenset(),
    )
    view_round_2 = merge_command_results(v1, {"res://root_bad.gd": v2_root_bad_broken})
    assert view_round_2.pending_pointers == []  # pointer 已消化
    assert view_round_2.gdscript_complete is False  # 但根因还在，项目没完成
    assert len(view_round_2.root_cause_errors) == 1

    # 第三轮：Agent 把 root_bad.gd 修好了，重新对它跑一次 V2 是 CLEAN
    v2_root_bad_fixed = filter_verify_output("", "", command="V2", autoload_keys=frozenset())
    view_round_3 = merge_command_results(v1, {"res://root_bad.gd": v2_root_bad_fixed})
    assert view_round_3.root_cause_errors == []
    assert view_round_3.pending_pointers == []
    assert view_round_3.gdscript_complete is True  # 根因空、pending 空，真正完成
