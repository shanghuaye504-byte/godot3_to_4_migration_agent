# editandfixguard

Agent 对工作区的唯一写通道，以及落盘前的 fix_guard。行为以 `inline_tools/docs/edit_and_fix_guard.md` 为准。实现顺序以本目录 `NEXT_STEP.md` 为准：上一步验收全部勾完，才做下一步。给 Codex 的范围和检索清单在 `AGENTS.md`，逐步 prompt 在 `CODEX_PROMPTS.md`。

本目录不是子模块：没有 `pyproject.toml`，不起 MCP server。依赖写在仓库根的 `pyproject.toml`。

宿主 `import inline_tools.editandfixguard`。模型可见参数只有设计书 schema 里的那些。下列参数由宿主作为关键字参数注入，不出现在模型 schema 里：

- `project_root`
- `round`
- `root_cause_errors`
- `pointers`
- `sig_before`
- `sig_after`
- `baseline_sha`

## 目标文件

```text
editandfixguard/
├── README.md
├── NEXT_STEP.md
├── __init__.py
├── edit.py            # 流水线 0–11
├── precheck.py        # 第 0 步
├── anchor.py          # 第 1–4 步
├── git_txn.py         # 第 6–9 步与 revert
├── sync_index.py      # 第 10 步
├── guard.py
├── symbols.py
├── rules_db.py
├── scene_names.py
└── tests/
```

当前只有本说明、`NEXT_STEP.md` 和空的 `__init__.py`。上表其余文件在对应 step 里新增。

## 明确不做

- 不给模型 Bash、裸 git、Godot argv。
- 不 `git init`，不 wipe `*.uid`，不写 `.gitignore`，不创建 baseline。
- 不修改 `GdscriptParser` 的「`has_error` 则抛异常、不返回半套符号」约定。
- 不把 `.tscn` / `.tres` 送进 tree-sitter，不把场景边写入 `symbols`。
- 不实现 trace 数据库。审计落在 commit message 和返回 JSON。
- `rule_id` 只做只读存在性检查。retrieve 工具不在本目录。
