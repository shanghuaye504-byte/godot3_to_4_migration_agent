"""Step 3 的 find-symbol 场景引用验收。尚未写断言。

见 codebase_index/NEXT_STEP.md Step 3：
- class_name、func、脚本路径在场景里被引用时都能带回
- scene_usage_count 是全表计数；超过 50 条时 scene_usage_truncated 为 true
- 符号已从 .gd 删除但场景仍引用：退出码 0，matches 为空，scene_usages 非空
- 没有场景引用时 matches 的字段与改之前一致，line 仍是 0-based
- 重跑 index/tests/test_queries.py、test_connection.py、test_watcher_debounce.py 仍通过
- call-chain 与 class-hierarchy 的返回不变
"""
