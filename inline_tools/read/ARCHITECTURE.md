# read 的功能边界与验收

函数尚未实现。本文件是实现时必须满足的契约，不另开行为。

## 1. 签名

宿主注入 `project_root`。模型侧没有这个参数。

```text
read(project_root, path, line_from=1, line_to=None)
  → {
      "path": "res://scripts/player.gd",
      "lines": [{"n": 12, "text": "    velocity = ..."}],
      "total_lines": 142,
      "truncated": false
    }
```

| 字段 | 含义 |
| --- | --- |
| `path` | 模型给出的路径。`res://...`，或相对 `project_root` 的路径 |
| `line_from` | 起始行，1-based，含本行。默认 1 |
| `line_to` | 结束行，1-based，含本行。`None` 表示读到文件尾 |
| `lines[].n` | 该行在文件中的绝对行号，不是本次切片里的第几条 |
| `lines[].text` | 该行原文，不含由本工具另加的行号前缀 |
| `total_lines` | 文件总行数，不是本次返回的行数 |
| `truncated` | 因单次上限没读完请求区间时为 `true` |

不采用批量 `slices`。一次调用只读一个文件的一段。

## 2. 行为

- 实现是按行切片读文件。不经过 codeindex，不调用 `rg`，不跑 Godot。
- `line_from` 必须 ≥ 1。`line_to` 若给出，必须 ≥ `line_from`。否则是调用错误，不返回一段看起来成功的空切片。
- `line_to` 为 `None` 时读到文件尾，但仍受单次上限约束。
- 单次最多返回 2000 行。请求区间更长时，从 `line_from` 起返回 2000 行，`truncated=true`。早期草图里的 `limit=400` 不采用。
- `text` 必须与文件该行逐字一致（含缩进）。GDScript 缩进敏感，差一个空白以后的锚定编辑就会对不上。本工具不改写、不裁切行尾以外的内容；行尾的换行符不放进 `text`。
- 返回的 `path` 规范成 `res://` 相对路径。

## 3. 拒绝与错误

失败不返回 `lines: []` 冒充成功。用结构化错误，至少包含稳定的 `code`：

| 情况 | `code` |
| --- | --- |
| `realpath` 之后不在 `project_root` 内 | `PATH_ESCAPE` |
| 路径落在 `.godot/`、`.import/`、`.codeindex/` | `PATH_FORBIDDEN` |
| 文件不存在 | `FILE_NOT_FOUND` |
| `line_from` < 1，或 `line_to` < `line_from` | `BAD_RANGE` |

`res://foo.gd` 与 `foo.gd` 在同一工作区下指同一个文件。禁止目录对两种写法都拒绝。

## 4. 明确不做

- 不写盘。调用前后该文件字节不变。
- 不搜索。定位靠 `grep`。
- 不解析场景、不校验脚本、不返回符号表。
- 一次调用不读多个文件。

## 5. 验收

对应 `tests/test_read.py`（文件已建，断言未写）。实现后这些必须成立：

1. 请求第 2–4 行时，`lines` 的 `n` 依次为 2、3、4，且 `text` 与文件原文逐字相同。
2. 文件超过 2000 行且 `line_to` 为空时，返回恰好 2000 行，`truncated=true`，`total_lines` 仍是文件真实行数。
3. 文件不存在时 `code=FILE_NOT_FOUND`，不是空 `lines`。
4. `../` 逃出工作区时 `code=PATH_ESCAPE`，不读到工作区外的文件。
5. `.godot/`、`.import/`、`.codeindex/` 下的路径均为 `PATH_FORBIDDEN`。
6. `res://` 与相对路径读同一文件，`lines` 相同。
7. 调用前后目标文件字节不变。
