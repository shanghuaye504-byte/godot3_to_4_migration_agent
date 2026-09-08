"""db 子包：schema.sql 是 schema 唯一权威来源。

读法（SQL 术语 + player.gd 逐行填表）见 index/docs/schema_walkthrough.md。
权限边界：writer.py 是唯一允许写库的模块，queries.py 只读。
"""
