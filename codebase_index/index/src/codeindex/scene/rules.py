"""L4：场景 ERROR。每次现算，不把问题缓存进数据库。

尚未实现。验收见 codebase_index/NEXT_STEP.md 的 Step 4。

以后负责：
- 把语法级 P_ 问题提升为 E_PARSE_*。
- 判断根数量、资源编号、父路径、未转换的 format、旧类名黑名单、嵌套成环。
- 文件没读完，或问题落在看不全的子树上时弃权，写入 suppressed_checks。
- 弃权看节点路径，不看 subject 字符串。
- migration_rules_db 缺失时跳过 E_UNMIGRATED_TYPE，并标明 rules_unavailable。
- 不 import rag。
"""
