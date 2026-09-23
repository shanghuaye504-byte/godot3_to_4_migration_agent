# grep 的功能边界与验收

函数尚未实现。本文件是实现时必须满足的契约，不另开行为。

## 1. 签名

宿主注入 `project_root`。模型侧没有这个参数，也不能传入 argv。

```text
grep(project_root, pattern=None, glob=None, path=None, context=0, max_results=100)
  → {
      "matches": [
        {
          "path": "res://levels/l1.tscn",
          "line": 14,
          "text": "[node name=\"Player\" type=\"KinematicBody2D\"]",
          "context_before": [],
          "context_after": []
        }
      ],
      "total_matches": 3,
      "truncated": false,
      "files_only": false
    }
```

| 字段 | 含义 |
| --- | --- |
| `pattern` | 搜索串。`None` 或空字符串表示不搜内容，只列文件 |
| `glob` | 传给 `rg -g` 的过滤。`None` 表示不额外限制后缀 |
| `path` | 可选子树，相对工作区或 `res://`。`None` 表示整个工作区 |
| `context` | 命中行前后各带几行。默认 0 |
| `max_results` | 最多返回几条。默认 100 |
| `matches[].path` | `res://` 路径 |
| `matches[].line` | 1-based。只列文件时省略 |
| `matches[].text` | 命中行原文。只列文件时省略 |
| `context_before` / `context_after` | 上下文字符串列表。`context=0` 时为空列表 |
| `total_matches` | 截断前的命中总数；列文件时为文件数 |
| `truncated` | 因上限没把命中全部返回时为 `true` |
| `files_only` | `pattern` 为空时为 `true` |

## 2. 两种模式

有 `pattern`：搜索。`files_only=false`。`matches` 带 `path`、`line`、`text`。

`pattern` 为 `None` 或 `""`：列文件。`files_only=true`。`matches` 里只有 `path`，没有 `line` / `text`。这就是被合并进来的 glob，不再单开工具。

当前 codeindex 不索引 `.tscn` / `.tres` / `.gdshader`。在场景索引落地之前，本工具是模型看见这些后缀的通道。它只返回文本命中或路径，不解析场景结构。

## 3. 进程怎么起

底层是 `rg`，参数是列表，不是拼进 shell 的字符串。因此模型给的 `pattern` 不会被解释成管道或重定向。

工作目录是 `project_root`。

有 pattern 时等价于：

```text
rg --json -g '!.godot/**' -g '!.import/**' -g '!.codeindex/**'
   [--glob 模型给出的 glob]
   [--path 解析后的子树]
   -C <context>
   -e <pattern>
```

无 pattern 时等价于：

```text
rg --files -g '!.godot/**' -g '!.import/**' -g '!.codeindex/**'
   [--glob 模型给出的 glob]
   [--path 解析后的子树]
```

上面是参数含义，不是让模型填写的命令行。实现解析 `rg --json` 的 NDJSON，只收集 `match` 事件。

`rg` 默认遵守 `.gitignore`。不额外打开网络。

## 4. 上限

| 参数 | 默认 | 硬上限 | 超过时 |
| --- | --- | --- | --- |
| `max_results` | 100 | 500 | 按 500 截断，`truncated=true`。调用方传入更大的数也不得突破 500 |
| `context` | 0 | 5 | 按 5 执行，不把请求的更大窗口返回出去 |

`max_results` < 1 视为调用错误（`code=BAD_LIMIT`），不返回空成功。`context` < 0 同样是 `BAD_LIMIT`。

命中条数超过实际采用的 `max_results` 时，`matches` 只含前 N 条，`truncated=true`。`total_matches` 仍报告截断前的数量；若 `rg` 无法在不读完全部结果时给出精确总数，则 `total_matches` 等于已看到的条数，且 `truncated=true`，不得把截断后的长度说成总数。

## 5. 路径

`path` 使用与 `read` 相同的工作区规则：`res://` 或相对路径，`realpath` 后必须在 `project_root` 内，且不得落在 `.godot/`、`.import/`、`.codeindex/`。

| 情况 | `code` |
| --- | --- |
| `path` 逃出工作区 | `PATH_ESCAPE` |
| `path` 落在三个禁止目录 | `PATH_FORBIDDEN` |
| `max_results` < 1 或 `context` < 0 | `BAD_LIMIT` |

搜索无命中是成功：`matches` 为空，`total_matches=0`，`truncated=false`。这和路径非法不是同一件事。

禁止目录下的文件既不能作为 `path`，也不会出现在结果里。

## 6. 明确不做

- 不写盘。调用前后工作区字节不变。
- 不用 Python 再实现一套搜索来代替 `rg`。
- 不把参数拼成一条 shell 命令。
- 不读文件的连续区间（那是 `read`）。`context` 只是命中行周围的有限原文，不能当作编辑锚点的来源。
- 不解析 `.tscn`，不做场景校验，不调用 codeindex 或 Godot。

## 7. 验收

对应 `tests/test_grep.py`（文件已建，断言未写）。实现后这些必须成立：

1. 有 pattern 时，命中含 `res://` 路径、1-based `line`、与文件一致的 `text`。
2. `pattern` 为空且 `glob` 为 `*.tscn` 时，`files_only=true`，结果只有 `.tscn` 路径，没有行号。
3. 命中数超过 `max_results` 时 `truncated=true`，返回条数等于该上限。传入大于 500 的 `max_results` 时，返回条数仍不超过 500。
4. 传入大于 5 的 `context` 时，前后文各自不超过 5 行。
5. 结果不包含 `.godot/`、`.import/`、`.codeindex/` 下的路径；`path` 指向这些目录或工作区外时返回对应错误码，而不是空命中。
6. 启动 `rg` 的参数是 argv 列表。`pattern` 里含 `;`、`|`、`$()` 时仍只作为 `-e` 的一个参数，不经过 shell。
7. 调用前后工作区字节不变。
8. 能在 `.tscn` 正文里命中类型名（例如 `KinematicBody2D`），因为当前索引不覆盖该后缀。
