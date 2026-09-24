"""Step 3 落库验收清单。尚未写断言。

见 codebase_index/NEXT_STEP.md Step 3：
- res://、相对路径、:: 后缀解析正确；只有 uid 没有 path 时 resolved_file 为空且不报 E_EXT_PATH_MISSING
- 一批里夹一个坏场景时，其他 .gd 与好场景仍提交；坏场景是 MALFORMED，不是整批回滚
- 增量 sync 的 scene_* 与全量重建逐行一致
- .tscn / .tres 不出现在 files 表
- 超过 4MB 为 SKIPPED_OVERSIZE；含 NUL 为 BINARY；二者不产生语法级洪水
"""
