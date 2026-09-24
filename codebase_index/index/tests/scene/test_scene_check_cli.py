"""Step 5 的 scene-check 命令验收。尚未写断言。

见 codebase_index/NEXT_STEP.md Step 5：
- 传入 a.gd 时包含引用它的场景上的问题，不包含无关场景上新造的问题
- 有 regression 时退出码仍是 0
- db 不存在时退出码是 2
- 重跑 index/tests/test_queries.py：无场景引用时 find-symbol 的 matches 与退出码不变
"""
