# tests

这里只有空文件，没有断言，也没有可运行的用例。验收标准写在工具文档里，实现时再填。

| 文件 | 将来要覆盖的文档 |
| --- | --- |
| `test_read.py` | `read/ARCHITECTURE.md` 第 5 节的 7 条 |
| `test_grep.py` | `grep/ARCHITECTURE.md` 第 7 节的 8 条 |

不要在本目录加 `pyproject.toml`。测试以后由仓库根的 pytest 收集。
