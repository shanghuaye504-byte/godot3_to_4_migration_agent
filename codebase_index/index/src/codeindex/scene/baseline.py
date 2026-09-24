"""L5：冻结基线，并区分新错误与旧账。

尚未实现。验收见 codebase_index/NEXT_STEP.md 的 Step 5。

以后负责：
- 在转换器之后、模型改文件之前，把当时的错误指纹写入 scene_baseline。
- 同时把当时每个脚本的 class_name 和 func 写入 scene_member_baseline。
- 这两张表冻结后只读，重新索引不得改写它们。
- 现在有、快照没有的错误是 regression；两边都有的是旧账；快照有、现在没有的是 fixed。
- E_MEMBER_GONE 只比较 class 与 func。引擎自带名字不在快照里，不报。
- 目标脚本语法失败时弃权。
"""
