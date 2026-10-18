# editandfixguard：当前协作入口

本文件管辖本目录。根语言、目录、依赖和文档规则继续有效。

## 本轮依据

- 按根 LANDMARKS 的 S06/S07/S08/S11 及本级 LANDMARKS 执行；问题与复现见本级 DEFECTS。
- 旧 NEXT_STEP、edit_and_fix_guard 设计书用于理解既有实现；若与本轮经代码核对的修复指导冲突，以当前用户要求和新路标为准。不再限定只做旧清单第一个 Step。
- 不因旧测试已通过就忽略新的反例；先写反例，断言文件字节/HEAD/工作树，再修代码并同步 README。

## 仍有效的边界

- read/grep/_workspace 的既有路径边界保持；唯一写通道是 edit，输入 Hunk/create/revert。
- 模型不得获得 Bash、裸 Git、自由 Godot argv；工作区和规则/索引路径由宿主注入。
- 本工具不初始化仓库、不擦 UID、不写 ignore、不创建迁移基线；这些属于 L0。
- 本目录修复仅改必要的守卫/事务/同步；索引 parser 和 verify 的修复到其各自步骤完成，不在此复制一套实现。
- 测试放本目录 tests；不新建 pyproject；场景不送 Tree-sitter，规则库只读。
