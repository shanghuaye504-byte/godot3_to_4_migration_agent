"""L1：场景文档模型。

尚未实现。验收见 codebase_index/NEXT_STEP.md 的 Step 1。

以后负责：
- 把 lexer 的值收成 Section / SceneDoc。
- heading 上的键放 attrs，块内的行放 props 列表（保序，允许重复键）。
- 只记录语法级问题：字符串未闭合、括号未配平、方括号损坏、
  缺少文件头、头之前出现键值、Git 冲突标记。
- 不认识的 section 名不升成 ERROR。
- 不判断引用是否有效。
"""
