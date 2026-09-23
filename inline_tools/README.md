# inline_tools — 迁移 Agent 的原生只读工具

本目录是仓库里的一个普通 Python 包。宿主以后直接 `import inline_tools.read` / `import inline_tools.grep`。

它不是子模块：没有 `pyproject.toml`，没有 `src/` 布局，也不起 MCP server。依赖记在仓库根，不在这里再导出一层包。

当前只建了两个只读工具的目录和文档，**还没有函数实现**。

| 工具 | 位置 | 作用 |
| --- | --- | --- |
| `read` | `read/` | 按连续行区间读一个文件，带绝对行号 |
| `grep` | `grep/` | 在工作区里搜索或列文件；底层是固定参数的 `rg` |

整体边界见 [ARCHITECTURE.md](ARCHITECTURE.md)。各工具的签名、禁止事项和验收见各自目录下的 `ARCHITECTURE.md`。

`DESIGN_NOTES.md` 里的目录章（`pyproject.toml`、`src/inline_tools/tools/`、MCP server）作废，不要照着建。该文件其余关于 edit / guard 的长文先留着，但本步不实现那些工具，也不为它们建文件夹。
