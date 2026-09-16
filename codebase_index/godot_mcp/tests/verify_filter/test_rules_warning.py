"""`rules/warning.py` 的纯函数测试（方案文档 §7.8，R7；补齐的规则文件对应的补齐测试）。

覆盖要点：
- 普通 `WARNING:` 事件（非 UID 簇根）→ `drop_reason="warning_not_in_reward"`，事件
  本身保留在结果里（不像 R2/R3/R4 那样从"root_cause 候选"里物理消失）。
- 已被 R5（`uid_cluster.py`）提升为 UID 簇根的 WARNING：本规则不得覆盖/降级
  它——必须保持 `drop_reason=None`（唯一"文案是 WARNING、但代表真实问题"的例外）。
"""

from __future__ import annotations

from godot_mcp.verify_filter.models import ClassifiedEvent
from godot_mcp.verify_filter.parse import classify, parse_raw_events
from godot_mcp.verify_filter.rules.uid_cluster import apply_uid_cluster_rule
from godot_mcp.verify_filter.rules.warning import apply_warning_downgrade_rule


def _ordinary_warning() -> ClassifiedEvent:
    return ClassifiedEvent(
        prefix="WARNING",
        message="UNUSED_PARAMETER: The parameter 'foo' is never used.",
        at_function="GDScript::_parse",
        at_location="res://player.gd:12",
        res_path="res://player.gd",
        target_res_path=None,
        line_in_project=12,
        engine_location=None,
        source_stream="stderr",
        raw_block="",
        kind="warning",
        symbol=None,
        local_signature="sig",
        role="root_cause",  # classify() 的中性默认值
    )


def test_ordinary_warning_gets_drop_reason_but_keeps_role():
    result = apply_warning_downgrade_rule([_ordinary_warning()])
    assert result[0].drop_reason == "warning_not_in_reward"
    assert result[0].role == "root_cause"  # 不改 role，只标 drop_reason


def test_uid_cluster_root_not_downgraded(load_fixture):
    classified = classify(parse_raw_events("", load_fixture("sample_i_uid_duplicate_cluster.log")))
    after_uid = apply_uid_cluster_rule(classified)
    result = apply_warning_downgrade_rule(after_uid)

    cluster_root = [e for e in result if e.cluster_id is not None and e.role == "root_cause"]
    assert len(cluster_root) == 1
    assert cluster_root[0].drop_reason is None
