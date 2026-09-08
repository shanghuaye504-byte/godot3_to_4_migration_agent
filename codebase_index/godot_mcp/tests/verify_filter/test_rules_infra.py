"""`rules/infra.py` 的纯函数测试（方案文档 §7.7）。对应 §10 样例 I 里的 debugger 行。

覆盖要点：
- 样例 I 末尾的 `Plugin is not attached to debugger.` → `role="infra_noise"`，
  `drop_reason="debugger_plugin_detached"`，不进入 `root_cause_errors`。
- 该行不影响同一份日志里其它事件（尤其是 R5 压缩出的 UID 簇根因）的角色判断，两条
  规则互不干扰（顺序：先 R5 后 R6，与 §7 流水线一致）。
"""

from __future__ import annotations

from godot_mcp.verify_filter.parse import classify, parse_raw_events
from godot_mcp.verify_filter.rules.infra import apply_debugger_plugin_rule
from godot_mcp.verify_filter.rules.uid_cluster import apply_uid_cluster_rule


def test_sample_i_debugger_plugin_dropped(load_fixture):
    classified = classify(parse_raw_events("", load_fixture("sample_i_uid_duplicate_cluster.log")))
    after_uid_cluster = apply_uid_cluster_rule(classified)
    result = apply_debugger_plugin_rule(after_uid_cluster)

    debugger_events = [e for e in result if "Plugin is not attached" in e.message]
    assert len(debugger_events) == 1
    assert debugger_events[0].role == "infra_noise"
    assert debugger_events[0].drop_reason == "debugger_plugin_detached"

    root_causes = [e for e in result if e.role == "root_cause"]
    assert len(root_causes) == 1
    assert "UID duplicate detected" in root_causes[0].message
