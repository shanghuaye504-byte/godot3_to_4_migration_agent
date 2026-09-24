"""Step 4 的验收清单。尚未写断言。

见 codebase_index/NEXT_STEP.md Step 4：
- Godot 能 ResourceLoader.load 成功的文本场景不报 ERROR；只 load，不 instantiate
- 每一类 E 级故障的注入检出率 100%，code 正确，subject 不含行号
- 注入放进实例子树或继承场景时 ERROR 为 0，suppressed_checks 记下 node_path
- 仓库里有 class_name KinematicBody2D 时不报 E_UNMIGRATED_TYPE
- 未配置 migration_rules_db 时不报该错误，rules_unavailable 为 true
- 插删空行或注释不改变已有 fingerprint
- 同输入多次运行，problem 集合一致
- 重跑 index/tests/test_config.py：没有该字段的旧 yaml 仍能加载
"""
