"""错误身份签名 —— 只用 `local_signature`。

```text
normalized_message =
    把 message 里的 res://... 换成 <RES>
    把 Identifier not found: Foo / Identifier "Foo" / Class "Foo" 里的符号换成 <SYM>
    删除一切 :数字 形式的项目行号
    不删除引擎路径里的 cpp 行号（ERROR 跟的是引擎源码，行号固定，可作症状同一性依据）

local_signature = sha1(kind | res_path_or_empty | symbol_or_empty | normalized_message)
```

**行号不得进入签名**（patch 会移动行号，含行号的签名会让"同一个错误"看起来像新错误，
Agent/Gate 的震荡检测直接失效）；行号只保留在 `RawEvent.line_in_project`，只传给 LLM。

生产过滤、merge 去重、Gate 判定一律用 `local_signature`。不要再引入模板级哈希：
它会把 `Identifier not found: Config` 与 `Identifier not found: SomeMissingClass`
折成同一身份。
"""

from __future__ import annotations

import hashlib
import re

# 项目脚本行号：res://xxx.gd:12 形式里冒号后面的数字。不要动引擎 cpp 的 :46——那个行号是
# 引擎源码固定位置，同一症状（如 gdscript_resource_format.cpp:46）要保持稳定，属于
# 症状同一性依据的一部分，不在这里删除。
_PROJECT_RES_LINE = re.compile(r"(res://[^\s\"'():]+):\d+")
_PROJECT_RES_BARE = re.compile(r"res://[^\s\"'():]+")

# Identifier not found: Foo / Identifier "Foo" not declared.../ Class "Foo" hides...
_SYM_AFTER_COLON = re.compile(r"(Identifier not found: )(\S+)")
_SYM_QUOTED = re.compile(r"((?:Identifier|Class) \")([^\"]+)(\")")


def normalize_message(message: str, *, res_path: str | None = None, symbol: str | None = None) -> str:
    """把 message 里的 res:// 路径、符号名换成占位符，删掉项目行号；引擎 cpp 行号保留。

    `res_path`/`symbol` 参数目前不改变归一化结果（归一化只依据 message 本身的文本
    特征），保留这两个参数是为了让调用方在未来需要"用已知字段做更精确替换"时不必
    改函数签名；当前实现忽略它们，纯粹靠正则识别 message 里的 res:// 与符号片段。
    """
    text = message
    text = _PROJECT_RES_LINE.sub("<RES>", text)
    text = _PROJECT_RES_BARE.sub("<RES>", text)
    text = _SYM_AFTER_COLON.sub(r"\1<SYM>", text)
    text = _SYM_QUOTED.sub(r"\1<SYM>\3", text)
    return text


def local_signature(*, kind: str, res_path: str | None, symbol: str | None, normalized_message: str) -> str:
    """sha1(kind | res_path_or_empty | symbol_or_empty | normalized_message) 的十六进制摘要。"""
    payload = "|".join([kind, res_path or "", symbol or "", normalized_message])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()
