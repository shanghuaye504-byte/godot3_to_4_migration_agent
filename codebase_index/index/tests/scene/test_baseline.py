"""Step 5 快照与 E_MEMBER_GONE 验收。尚未写断言。

见 codebase_index/NEXT_STEP.md Step 5：
- 修好、弄坏、留下的条数分别等于 fixed、regression、pre_existing
- 文件头插入 100 行后旧问题仍是 pre_existing，regression 为空
- class_name 改名而场景 type 仍是旧名时有一条 regression；场景改成新名后消失
- 连接指向的函数改名且场景未改时有 regression；_ready 不报
- Sprite2D / CharacterBody2D 不产生 E_MEMBER_GONE
- 目标 .gd 语法失败时不报 E_MEMBER_GONE，并有 suppressed_checks
- 冻结后再索引，scene_member_baseline 仍是冻结时的成员
"""
