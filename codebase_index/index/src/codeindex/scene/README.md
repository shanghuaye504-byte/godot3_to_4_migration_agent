# scene

`.tscn` / `.tres` 的解析、落库和校验。属于现有 `codeindex` 包，没有单独的 `pyproject.toml`。

全部六层已实装。契约、弃权规则和实现顺序见 `codebase_index/NEXT_STEP.md`。

| 文件 | 层 | 以后做什么 |
| --- | --- | --- |
| `lexer.py` | L0 | 把文本切成带 span 的值（已实装） |
| `model.py` | L1 | 收成 `Section` / `SceneDoc`，记下语法级问题（已实装） |
| `resolve.py` | L2 | 节点路径、实例子树、引用边。不碰文件系统（已实装） |
| `schema.sql` | L3 | 场景旁路表。不改 `files` / `symbols` / `edges`（已实装） |
| `store.py` | L3 | 在已有写事务里写入和删除这些表（已实装） |
| `rules.py` | L4 | 现算 ERROR，按节点路径弃权（已实装） |
| `baseline.py` | L5 | 冻结快照、三分法、`E_MEMBER_GONE`（已实装） |
| `check.py` | L5 | 组装 `codeindex scene-check` 的 JSON（已实装） |
