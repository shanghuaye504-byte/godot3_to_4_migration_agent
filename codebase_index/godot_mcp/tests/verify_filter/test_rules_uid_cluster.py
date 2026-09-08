"""`rules/uid_cluster.py` 的纯函数测试（方案文档 §7.6）。对应 §10 的 T-I。

覆盖要点：
- T-I：样例 I（UID 重复簇）过滤后恰好 1 条 root_cause（`kind="resource_error"`，
  message 含 `UID duplicate detected`）；`Parse Error: Busy. [...]` 与
  `Failed loading resource: ...` 均被标记为 `role="cluster_member"`，不能把 5 条
  ERROR 当 5 个问题。
- 压缩后的那一条 root_cause：`res_path` 取字典序较小的那条路径，`cluster_id` 非空
  且与两个 `cluster_member` 的 `cluster_id` 相同。
- debugger plugin 行不属于簇成员（不匹配 res_path），扫描应在它之前停止。
- 没有 `UID duplicate detected` WARNING 时（合成样例）：本规则应无操作。
"""

from __future__ import annotations

from godot_mcp.verify_filter.parse import classify, parse_raw_events
from godot_mcp.verify_filter.rules.uid_cluster import apply_uid_cluster_rule


def test_t_i_uid_cluster_compresses_to_single_root_cause(load_fixture):
    classified = classify(parse_raw_events("", load_fixture("sample_i_uid_duplicate_cluster.log")))
    result = apply_uid_cluster_rule(classified)

    root_causes = [e for e in result if e.role == "root_cause" and "UID duplicate detected" in e.message]
    assert len(root_causes) == 1
    root = root_causes[0]
    assert root.kind == "resource_error"
    assert root.res_path == "res://main.tscn"  # main.tscn < sub.tscn 字典序
    assert root.cluster_id is not None

    members = [e for e in result if e.role == "cluster_member"]
    assert len(members) == 4  # 2×(Busy + Failed loading)
    for m in members:
        assert m.cluster_id == root.cluster_id
        assert m.drop_reason == "uid_duplicate_satellite"

    # debugger plugin 行没有被误吞成簇成员
    debugger_events = [e for e in result if "Plugin is not attached" in e.message]
    assert len(debugger_events) == 1
    assert debugger_events[0].role not in ("cluster_member",)


def test_no_uid_warning_is_noop(load_fixture):
    classified = classify(parse_raw_events("", load_fixture("sample_a_autoload_fp_cold.log")))
    result = apply_uid_cluster_rule(classified)
    assert [e.role for e in result] == [e.role for e in classified]
    assert all(e.cluster_id is None for e in result)
