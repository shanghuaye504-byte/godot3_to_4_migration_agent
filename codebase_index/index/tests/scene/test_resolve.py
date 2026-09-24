"""Step 2 的验收清单。尚未写断言。

见 codebase_index/NEXT_STEP.md Step 2：
- 多层嵌套、parent="."、同名兄弟时 node_by_path 与人工标注一致
- 0、1、2 个根时 root_paths 长度正确
- 继承场景、instance=、instance_placeholder 的未解析子树与 is_inherited 与标注一致
- ext_use / sub_use 条数等于字符串之外的 ExtResource(" / SubResource(" 次数
- resolve.py 不导入 os、pathlib、sqlite3
"""
