# tests/scene

场景解析与校验的测试。每一条要测什么见 `codebase_index/NEXT_STEP.md` 第 7 节对应的 Step。

| 文件 | 对应步骤 |
| --- | --- |
| `test_lexer_model.py` | Step 1（已实装，62 条全绿） |
| `test_resolve.py` | Step 2（已实装，51 条全绿） |
| `test_store.py` | Step 3 落库（已实装，11 条全绿） |
| `test_find_symbol_scene.py` | Step 3 的 find-symbol（已实装，8 条全绿） |
| `test_rules.py` | Step 4（已实装，33 条全绿） |
| `test_baseline.py` | Step 5 快照与成员差分（已实装，7 条全绿） |
| `test_scene_check_cli.py` | Step 5 的 CLI（已实装，5 条全绿） |
