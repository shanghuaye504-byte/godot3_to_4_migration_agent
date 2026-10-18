# codebase_index：当前协作入口

本文件管辖本目录及全部子目录。根 AGENTS 的语言、文档和两层依赖规则继续有效。

## 执行顺序

- 本轮用户要求的执行顺序见根 `LANDMARKS.md` S00→S25，本级 `LANDMARKS.md` 是范围导航，`DEFECTS.md` 是问题与复现入口。
- 旧 NEXT_STEP 的场景实现顺序和 SCENE_INDEX_TODO 只作历史资料；不再限定“只能改第一个旧 Step”。
- 为修复 IDX-01/IDX-02，可修改 GDScript parser/依赖存储；为修复 VER 系列，可修改 godot_mcp。每次只做当前步骤及必要测试，不顺带大改其他模块。

## 仍有效的边界

- 以实际代码与测试核对现状；旧 README/design 不当作功能已实现的证据。目标行为按新路标和独立反例验收。
- 场景保留在 index/src/codeindex/scene；不把 .tscn/.tres 送进 Tree-sitter，不将场景旁路关系混入脚本 symbols。
- scenecheckfixture 是孤立静态夹具，不用 ResourceLoader.load 验收；动态验证用完整项目夹具。
- 查询符号先 rg 定位相关函数；只读需要的文档，不大量引入旧 docs。
- 不在内部子目录新建 pyproject；新增依赖遵守根规则；修改代码后同步本目录 README。
