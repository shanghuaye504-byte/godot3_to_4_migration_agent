"""Step 1 的验收清单。尚未写断言。

见 codebase_index/NEXT_STEP.md Step 1：
- span 切片等于原文，行号列号与逐字节换行计数一致
- 去掉注释和空白后，每个字节都落在某个 span 里
- 格式矩阵：format 2 与 3、整数 id 与字符串 id、注释、多行 Packed 数组、
  theme_override_colors/font_color、libraries/""、字符串名、NodePath、
  Array[Node]([])、转义、空 NodePath、尾随逗号、CRLF、无尾换行
- 语料加随机截断或字节翻转时不抛未捕获异常，问题进 problems
- 每个 P_ 至少 1 个正例和 1 个易混淆反例
- PoolByteArray(...) 与 NotARealType(...) 保留为 call，不报语法错误
"""
