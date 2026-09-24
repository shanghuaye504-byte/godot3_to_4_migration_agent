"""L0：场景文本的词法。

把 .tscn / .tres 切成带 span 的值（字符串、数字、调用、数组、字典）。
多行值用括号深度切开，深度统计跳过字符串里的括号。
没见过的构造器保留为 call，不报语法错误。
不判断类型是否存在，不读磁盘，不调用 Godot。

契约见 codebase_index/NEXT_STEP.md 第 2 节。本模块永不抛异常：
词法问题通过 LexResult.problems 返回，调用方（L1）把它们记进 SceneDoc。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# 已知 section 名（NEXT_STEP 2.1）。不在这个列表里的记 W_UNKNOWN_SECTION，不升 ERROR。
KNOWN_SECTIONS = frozenset(
    {
        "gd_scene",
        "gd_resource",
        "ext_resource",
        "sub_resource",
        "node",
        "connection",
        "resource",
        "editable",
    }
)

GIT_CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")

_WHITESPACE = " \t\r\n"
_DIGITS = "0123456789"
_IDENT_START = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
_IDENT_CHARS = _IDENT_START + _DIGITS
_NUMBER_CHARS = _DIGITS + ".-+eExXaAbBcCdDfF"
_OPENERS = {"(": ")", "[": "]", "{": "}"}
_CLOSERS = {")": "(", "]": "[", "}": "{"}

ValueKind = Literal[
    "str",
    "strname",
    "nodepath",
    "int",
    "float",
    "bool",
    "null",
    "call",
    "array",
    "dict",
    "typed_array",
]


@dataclass(frozen=True)
class Span:
    """半开区间 [byte_start, byte_end)，行号列号 1-based，与 Godot 报错对齐。"""

    byte_start: int
    byte_end: int
    line: int
    col: int


@dataclass
class Value:
    """词法值。raw 恒等于 text[span.byte_start:span.byte_end]。"""

    kind: ValueKind
    raw: str
    span: Span
    name: str | None = None
    items: list["Value"] = field(default_factory=list)
    pairs: list[tuple["Value", "Value"]] = field(default_factory=list)


@dataclass
class Problem:
    """语法级问题。stage="lex" 由 L0 产生，stage="parse" 由 L1 产生。"""

    code: str
    message: str
    span: Span
    stage: str = "lex"


@dataclass
class PropLine:
    """一行（可能跨行）顶层键值：name = value。"""

    name: str
    name_span: Span
    value: Value
    span: Span


@dataclass
class HeaderLine:
    """一行 section 头。attrs 键开放，不做白名单。"""

    name: str
    attrs: dict[str, Value]
    span: Span
    inner_span: Span


@dataclass
class BlankLine:
    span: Span


@dataclass
class CommentLine:
    span: Span


@dataclass
class GarbageLine:
    """既不是 section 头也不是 k=v 的行。L1 决定记哪个 P_*。"""

    text: str
    span: Span


Line = HeaderLine | PropLine | BlankLine | CommentLine | GarbageLine


@dataclass
class LexResult:
    lines: list[Line]
    problems: list[Problem]


class _Lexer:
    def __init__(self, text: str) -> None:
        self.text = text
        self.n = len(text)
        self.pos = 0
        self.line = 1
        self.line_start = 0
        self.problems: list[Problem] = []

    # ---- 位置工具 -------------------------------------------------------

    def cur_line_col(self) -> tuple[int, int]:
        return self.line, self.pos - self.line_start + 1

    def _advance(self, ch: str) -> None:
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.line_start = self.pos

    # ---- 主循环 ---------------------------------------------------------

    def run(self) -> LexResult:
        lines: list[Line] = []
        while self.pos < self.n:
            line = self._lex_line()
            if line is not None:
                lines.append(line)
        return LexResult(lines=lines, problems=self.problems)

    def _lex_line(self) -> Line | None:
        start = self.pos
        line_no, col = self.cur_line_col()
        while self.pos < self.n and self.text[self.pos] in " \t":
            self.pos += 1
        if self.pos >= self.n:
            if self.pos > start:
                return BlankLine(Span(start, self.pos, line_no, col))
            return None
        ch = self.text[self.pos]
        if ch == "\n":
            self._advance(ch)
            return BlankLine(Span(start, self.pos, line_no, col))
        if ch == ";":
            self._skip_to_eol()
            return CommentLine(Span(start, self.pos, line_no, col))
        if ch == "[":
            header = self._try_header(start, line_no, col)
            if header is not None:
                return header
            return self._garbage_line(start, line_no, col)
        prop = self._try_prop(start, line_no, col)
        if prop is not None:
            return prop
        return self._garbage_line(start, line_no, col)

    def _skip_to_eol(self) -> None:
        while self.pos < self.n and self.text[self.pos] != "\n":
            self.pos += 1
        if self.pos < self.n:
            self._advance("\n")

    def _garbage_line(self, start: int, line_no: int, col: int) -> GarbageLine:
        content_start = self.pos
        self._skip_to_eol()
        return GarbageLine(
            text=self.text[content_start : self.pos],
            span=Span(start, self.pos, line_no, col),
        )

    # ---- section 头 ------------------------------------------------------

    def _try_header(self, start: int, line_no: int, col: int) -> HeaderLine | None:
        """解析 `[name k=v ...]`。结构不符时返回 None，由调用方降级为 garbage。"""
        saved = self.pos
        self.pos += 1  # 吃 '['
        name_start = self.pos
        if self.pos < self.n and self.text[self.pos] in _IDENT_START:
            while self.pos < self.n and self.text[self.pos] in _IDENT_CHARS:
                self.pos += 1
        name = self.text[name_start : self.pos]
        if not name:
            self.pos = saved
            return None
        attrs: dict[str, Value] = {}
        while True:
            while self.pos < self.n and self.text[self.pos] in " \t":
                self.pos += 1
            if self.pos >= self.n or self.text[self.pos] in "\n;":
                self.pos = saved
                return None
            if self.text[self.pos] == "]":
                self.pos += 1
                self._skip_to_eol()
                inner = Span(start + 1, self.pos - 1, line_no, col + 1)
                return HeaderLine(
                    name=name,
                    attrs=attrs,
                    span=Span(start, self.pos, line_no, col),
                    inner_span=inner,
                )
            kv = self._try_header_attr()
            if kv is None:
                self.pos = saved
                return None
            key, value = kv
            attrs[key] = value

    def _try_header_attr(self) -> tuple[str, Value] | None:
        if self.pos >= self.n or self.text[self.pos] not in _IDENT_START:
            return None
        key_start = self.pos
        while self.pos < self.n and self.text[self.pos] in _IDENT_CHARS:
            self.pos += 1
        key = self.text[key_start : self.pos]
        while self.pos < self.n and self.text[self.pos] in " \t":
            self.pos += 1
        if self.pos >= self.n or self.text[self.pos] != "=":
            return None
        self.pos += 1
        while self.pos < self.n and self.text[self.pos] in " \t":
            self.pos += 1
        value = self.parse_value()
        if value is None:
            return None
        return key, value

    # ---- 属性行 ----------------------------------------------------------

    def _try_prop(self, start: int, line_no: int, col: int) -> PropLine | None:
        saved = self.pos
        name_start = self.pos
        seen_chars = False
        while self.pos < self.n:
            ch = self.text[self.pos]
            if ch in _IDENT_CHARS or ch in "/-.":
                self.pos += 1
                seen_chars = True
            elif ch == '"':
                if not self._skip_string():
                    break
                seen_chars = True
            else:
                break
        if not seen_chars:
            self.pos = saved
            return None
        name_end = self.pos
        while self.pos < self.n and self.text[self.pos] in " \t":
            self.pos += 1
        if self.pos >= self.n or self.text[self.pos] != "=":
            self.pos = saved
            return None
        self.pos += 1
        while self.pos < self.n and self.text[self.pos] in " \t":
            self.pos += 1
        if self.pos >= self.n or self.text[self.pos] in "\n;":
            self.pos = saved
            return None
        value = self.parse_value()
        if value is None:
            self.pos = saved
            return None
        self._skip_to_eol()
        return PropLine(
            name=self.text[name_start:name_end],
            name_span=Span(name_start, name_end, line_no, name_start - start + col),
            value=value,
            span=Span(start, self.pos, line_no, col),
        )

    # ---- 值 --------------------------------------------------------------

    def parse_value(self) -> Value | None:
        """递归下降解析一个值。返回 None 表示起始字符不构成任何值。"""
        self._skip_inline_ws_and_comments()
        if self.pos >= self.n:
            return None
        ch = self.text[self.pos]
        if ch == '"':
            return self._string_like("str")
        if ch == "&" and self.pos + 1 < self.n and self.text[self.pos + 1] == '"':
            return self._string_like("strname")
        if ch == "^" and self.pos + 1 < self.n and self.text[self.pos + 1] == '"':
            return self._string_like("nodepath")
        if ch == "[":
            return self._array()
        if ch == "{":
            return self._dict()
        if ch in _DIGITS or (
            ch in "+-" and self.pos + 1 < self.n and self.text[self.pos + 1] in _DIGITS + "."
        ):
            return self._number()
        if ch == "." and self.pos + 1 < self.n and self.text[self.pos + 1] in _DIGITS:
            return self._number()
        if ch in _IDENT_START:
            return self._ident_value()
        return None

    def _skip_inline_ws_and_comments(self) -> None:
        while self.pos < self.n:
            ch = self.text[self.pos]
            if ch in _WHITESPACE:
                self._advance(ch)
            elif ch == ";":
                self._skip_to_eol()
            else:
                return

    def _skip_string(self) -> bool:
        """跳过一个已确认以 `"` 开头的字符串。返回是否闭合。"""
        self.pos += 1
        while self.pos < self.n:
            ch = self.text[self.pos]
            if ch == "\\":
                self.pos += 1
                if self.pos < self.n:
                    self._advance(self.text[self.pos])
                continue
            if ch == '"':
                self.pos += 1
                return True
            self._advance(ch)
        return False

    def _string_like(self, kind: ValueKind) -> Value:
        start = self.pos
        line_no, col = self.cur_line_col()
        if kind in ("strname", "nodepath"):
            self.pos += 1  # 吃 & 或 ^
        closed = self._skip_string()
        raw = self.text[start : self.pos]
        if not closed:
            self.problems.append(
                Problem(
                    code="P_UNTERMINATED_STRING",
                    message="字符串到文件末尾未闭合",
                    span=Span(start, self.pos, line_no, col),
                )
            )
        return Value(kind=kind, raw=raw, span=Span(start, self.pos, line_no, col))

    def _number(self) -> Value:
        start = self.pos
        line_no, col = self.cur_line_col()
        seen_dot = False
        seen_exp = False
        while self.pos < self.n and self.text[self.pos] in _NUMBER_CHARS:
            ch = self.text[self.pos]
            if ch == ".":
                seen_dot = True
            elif ch in "eE":
                seen_exp = True
            self.pos += 1
        raw = self.text[start : self.pos]
        kind: ValueKind = "float" if (seen_dot or seen_exp) else "int"
        return Value(kind=kind, raw=raw, span=Span(start, self.pos, line_no, col))

    def _ident_value(self) -> Value:
        start = self.pos
        line_no, col = self.cur_line_col()
        while self.pos < self.n and self.text[self.pos] in _IDENT_CHARS:
            self.pos += 1
        ident = self.text[start : self.pos]
        if ident in ("true", "false"):
            return Value(kind="bool", raw=ident, span=Span(start, self.pos, line_no, col))
        if ident == "null":
            return Value(kind="null", raw=ident, span=Span(start, self.pos, line_no, col))
        if ident == "Array" and self.pos < self.n and self.text[self.pos] == "[":
            return self._typed_array(start, line_no, col)
        if self.pos < self.n and self.text[self.pos] == "(":
            return self._call(ident, start, line_no, col)
        # 裸标识符：不是合法值，保留原文但不报语法错误
        return Value(kind="null", raw=ident, span=Span(start, self.pos, line_no, col))

    def _call(self, name: str, start: int, line_no: int, col: int) -> Value:
        self.pos += 1  # 吃 '('
        args = self._value_list(")")
        if self.pos > 0 and self.text[self.pos - 1] != ")" and self.pos >= self.n:
            self.problems.append(
                Problem(
                    code="P_UNBALANCED_BRACKET",
                    message=f"调用 {name}(...) 到文件末尾未闭合",
                    span=Span(start, self.pos, line_no, col),
                )
            )
        return Value(
            kind="call",
            raw=self.text[start : self.pos],
            span=Span(start, self.pos, line_no, col),
            name=name,
            items=args,
        )

    def _typed_array(self, start: int, line_no: int, col: int) -> Value:
        # self.pos 指向 "Array" 之后的 '['
        self.pos += 1
        type_start = self.pos
        while self.pos < self.n and self.text[self.pos] in _IDENT_CHARS:
            self.pos += 1
        type_name = self.text[type_start : self.pos]
        if self.pos < self.n and self.text[self.pos] == "]":
            self.pos += 1
        self._skip_inline_ws_and_comments()
        items: list[Value] = []
        if self.pos < self.n and self.text[self.pos] == "(":
            self.pos += 1
            items = self._value_list(")")
        return Value(
            kind="typed_array",
            raw=self.text[start : self.pos],
            span=Span(start, self.pos, line_no, col),
            name=f"Array[{type_name}]",
            items=items,
        )

    def _array(self) -> Value:
        start = self.pos
        line_no, col = self.cur_line_col()
        self.pos += 1  # 吃 '['
        items = self._value_list("]")
        if self.pos > 0 and self.text[self.pos - 1] != "]" and self.pos >= self.n:
            self.problems.append(
                Problem(
                    code="P_UNBALANCED_BRACKET",
                    message="数组到文件末尾未闭合",
                    span=Span(start, self.pos, line_no, col),
                )
            )
        return Value(
            kind="array",
            raw=self.text[start : self.pos],
            span=Span(start, self.pos, line_no, col),
            items=items,
        )

    def _dict(self) -> Value:
        start = self.pos
        line_no, col = self.cur_line_col()
        self.pos += 1  # 吃 '{'
        pairs: list[tuple[Value, Value]] = []
        self._skip_inline_ws_and_comments()
        if self.pos < self.n and self.text[self.pos] == "}":
            self.pos += 1
            return Value(
                kind="dict",
                raw=self.text[start : self.pos],
                span=Span(start, self.pos, line_no, col),
                pairs=pairs,
            )
        unclosed = False
        while True:
            key = self.parse_value()
            if key is None:
                if self._recover_or_eof(",}"):
                    unclosed = True
                    break
                if self.text[self.pos] == "}":
                    self.pos += 1
                    break
                self.pos += 1  # 吃 ','
                continue
            self._skip_inline_ws_and_comments()
            if self.pos >= self.n or self.text[self.pos] != ":":
                if self._recover_or_eof(",}"):
                    unclosed = True
                    break
                if self.text[self.pos] == "}":
                    self.pos += 1
                    break
                self.pos += 1  # 吃 ','
                continue
            self.pos += 1  # 吃 ':'
            value = self.parse_value()
            if value is None:
                self._recover_to(",}")
                value = Value(
                    kind="null",
                    raw="",
                    span=Span(self.pos, self.pos, *self.cur_line_col()),
                )
            pairs.append((key, value))
            self._skip_inline_ws_and_comments()
            if self.pos >= self.n:
                unclosed = True
                break
            ch = self.text[self.pos]
            if ch == ",":
                self.pos += 1
                self._skip_inline_ws_and_comments()
                if self.pos < self.n and self.text[self.pos] == "}":
                    self.pos += 1  # 尾随逗号
                    break
                continue
            if ch == "}":
                self.pos += 1
                break
            if self._recover_or_eof(",}"):
                unclosed = True
                break
            if self.text[self.pos] == "}":
                self.pos += 1
                break
            self.pos += 1  # 吃 ','
        if unclosed:
            self.problems.append(
                Problem(
                    code="P_UNBALANCED_BRACKET",
                    message="字典到文件末尾未闭合",
                    span=Span(start, self.pos, line_no, col),
                )
            )
        return Value(
            kind="dict",
            raw=self.text[start : self.pos],
            span=Span(start, self.pos, line_no, col),
            pairs=pairs,
        )

    def _value_list(self, closer: str) -> list[Value]:
        """解析 `v, v, ..., <closer>`。self.pos 在 opener 之后。返回前消费 closer。"""
        items: list[Value] = []
        self._skip_inline_ws_and_comments()
        if self.pos < self.n and self.text[self.pos] == closer:
            self.pos += 1
            return items
        while True:
            v = self.parse_value()
            if v is None:
                if self._recover_or_eof("," + closer):
                    break
            else:
                items.append(v)
            self._skip_inline_ws_and_comments()
            if self.pos >= self.n:
                break
            ch = self.text[self.pos]
            if ch == ",":
                self.pos += 1
                self._skip_inline_ws_and_comments()
                if self.pos < self.n and self.text[self.pos] == closer:
                    self.pos += 1  # 尾随逗号
                    break
                continue
            if ch == closer:
                self.pos += 1
                break
            if self._recover_or_eof("," + closer):
                break
            if self.text[self.pos] == closer:
                self.pos += 1
                break
            self.pos += 1  # 吃 ','
        return items

    def _recover_or_eof(self, chars: str) -> bool:
        """_recover_to 之后若到 EOF 返回 True。"""
        self._recover_to(chars)
        return self.pos >= self.n

    def _recover_to(self, chars: str) -> None:
        """错误恢复：前进到 chars 中任意一个字符或换行。跳过字符串内容。"""
        depth = 0
        while self.pos < self.n:
            ch = self.text[self.pos]
            if ch == "\n" and depth == 0:
                return
            if ch == '"':
                self._skip_string()
                continue
            if ch in _OPENERS:
                depth += 1
            elif ch in _CLOSERS:
                if depth == 0 and ch in chars:
                    return
                depth = max(0, depth - 1)
            elif depth == 0 and ch in chars:
                return
            self._advance(ch)


def lex_text(text: str) -> LexResult:
    """把 .tscn / .tres 文本切成带 span 的行序列。永不抛异常。"""
    return _Lexer(text).run()
