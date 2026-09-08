"""两级 signature —— 方案文档 §6。规格来自 N09（横向确认"随项目而变的只有 res:// 文件名"）。

```text
normalized_message =
    把 message 里的 res://... 换成 <RES>
    把 Identifier not found: Foo / Identifier "Foo" / Class "Foo" 里的符号换成 <SYM>
    删除一切 :数字 形式的项目行号
    不删除引擎路径里的 cpp 行号（ERROR 跟的是引擎源码，行号固定，可作症状同一性依据）

local_signature = sha1(kind | res_path_or_empty | symbol_or_empty | normalized_message)
noise_signature = sha1(kind | msg_template)
msg_template = normalized_message 再把 <RES>/<SYM> 之外残留的路径与数字全部换成占位符
```

**行号不得进入签名**（patch 会移动行号，含行号的签名会让"同一个错误"看起来像新错误，
Agent/Gate 的震荡检测直接失效）；行号只保留在 `RawEvent.line_in_project`，只传给 LLM。

**`noise_signature` 禁止用于生产过滤或 Gate 判定**：它会把 `Identifier not found: Config`
与 `Identifier not found: SomeMissingClass` 折成同一模板。`local_signature` 才是项目内
去重、震荡检测、retry 计数的唯一依据（`verifier_retry_gate_scheme.md` §9 第 5 条）。
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

# 残留数字（非引擎 cpp 行号）：独立单词形式的十进制数字。
_STANDALONE_NUMBER = re.compile(r"(?<![\w./])\d+(?![\w./])")

# 引擎源码位置：xxx.cpp:NN / xxx.h:NN / xxx.mm:NN —— 这些行号必须保留，不参与占位符化。
_ENGINE_LOCATION = re.compile(r"[\w./]+\.(?:cpp|h|mm):\d+")


def normalize_message(message: str, *, res_path: str | None = None, symbol: str | None = None) -> str:
    """把 message 里的 res:// 路径、符号名换成占位符，删掉项目行号；引擎 cpp 行号保留。

    `res_path`/`symbol` 参数目前不改变归一化结果（归一化只依据 message 本身的文本
    特征），保留这两个参数是为了让调用方在未来需要"用已知字段做更精确替换"时不必
    改函数签名；当前实现忽略它们，纯粹靠正则识别 message 里的 res:// 与符号片段。
    """
    text = message
    # 1) res://xxx:NN → <RES>（先处理带行号的，再处理不带行号的裸路径）
    text = _PROJECT_RES_LINE.sub("<RES>", text)
    text = _PROJECT_RES_BARE.sub("<RES>", text)
    # 2) Identifier not found: Foo → Identifier not found: <SYM>
    text = _SYM_AFTER_COLON.sub(r"\1<SYM>", text)
    # 3) Identifier "Foo" / Class "Foo" → Identifier "<SYM>" / Class "<SYM>"
    text = _SYM_QUOTED.sub(r"\1<SYM>\3", text)
    return text


def msg_template(normalized: str) -> str:
    """在 `normalize_message` 的基础上，把残留的路径/数字也占位符化，产出噪声模板。

    保留引擎 cpp/h/mm 源码位置（`_ENGINE_LOCATION`）不变——它是"同一症状"的稳定依据；
    其余独立出现的十进制数字（如未被 §5.2 识别的行号/计数）换成 `<NUM>`。
    """
    # 先保护引擎位置片段，避免被后面的数字占位符规则误伤
    engine_spans = list(_ENGINE_LOCATION.finditer(normalized))
    if not engine_spans:
        return _STANDALONE_NUMBER.sub("<NUM>", normalized)

    pieces: list[str] = []
    cursor = 0
    for m in engine_spans:
        before = normalized[cursor : m.start()]
        pieces.append(_STANDALONE_NUMBER.sub("<NUM>", before))
        pieces.append(m.group(0))
        cursor = m.end()
    pieces.append(_STANDALONE_NUMBER.sub("<NUM>", normalized[cursor:]))
    return "".join(pieces)


def local_signature(*, kind: str, res_path: str | None, symbol: str | None, normalized_message: str) -> str:
    """sha1(kind | res_path_or_empty | symbol_or_empty | normalized_message) 的十六进制摘要。"""
    payload = "|".join([kind, res_path or "", symbol or "", normalized_message])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def noise_signature(*, kind: str, template: str) -> str:
    """sha1(kind | msg_template) 的十六进制摘要。仅供实验期 BG 减法使用，不进生产过滤/Gate。"""
    payload = "|".join([kind, template])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()
