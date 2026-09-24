"""L3：把场景模型写入已有的 SQLite 事务。

尚未实现。验收见 codebase_index/NEXT_STEP.md 的 Step 3。

以后负责：
- 由 writer.reindex_batch 在同一个事务里调用。本模块自己不 commit。
- 写入或删除 scene_* 行。不往 files 表插 .tscn / .tres。
- 含 NUL 记 BINARY，单文件超过 4MB 记 SKIPPED_OVERSIZE。
- 单个场景失败只记 MALFORMED，不把整批事务弄回滚。
- 解析 res://、相对路径和 :: 后缀。只有 uid、没有 path 时 resolved_file 为空。
"""
