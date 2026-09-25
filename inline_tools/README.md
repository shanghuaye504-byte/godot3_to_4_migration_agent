# inline_tools — 迁移 Agent 的原生只读工具

本目录是仓库里的一个普通 Python 包。宿主以后直接 `import inline_tools.read` / `import inline_tools.grep`。

它不是子模块：没有 `pyproject.toml`，没有 `src/` 布局，也不起 MCP server。依赖记在仓库根，不在这里再导出一层包。

`read` 与 `grep` 已实现。`editandfixguard` 目前只有文档和空包，写通道按该目录的 `NEXT_STEP.md` 逐步落地。

| 工具 | 位置 | 作用 |
| --- | --- | --- |
| `read` | `read/` | 按连续行区间读一个文件，带绝对行号 |
| `grep` | `grep/` | 在工作区里搜索或列文件；底层是固定参数的 `rg` |
| `edit` / `fix_guard` | `editandfixguard/` | 唯一写通道和落盘前守卫。按该目录 `NEXT_STEP.md` 逐步实现，当前只有文档和空包 |

整体边界见 [ARCHITECTURE.md](ARCHITECTURE.md)。只读工具的签名、禁止事项和验收见各自目录下的 `ARCHITECTURE.md`。写通道的行为见 `docs/edit_and_fix_guard.md`，实现顺序见 `editandfixguard/NEXT_STEP.md`。

`DESIGN_NOTES.md` 里的目录章（`pyproject.toml`、`src/inline_tools/tools/`、MCP server）作废，不要照着建。该文件第 7 节的旧流水线也不再作为实现依据。
