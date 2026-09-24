"""L1：场景文档模型。

把 lexer 的值收成 Section / SceneDoc。
heading 上的键放 attrs，块内的行放 props 列表（保序，允许重复键）。
只记录语法级问题：字符串未闭合、括号未配平、方括号损坏、
缺少文件头、头之前出现键值、Git 冲突标记。
不认识的 section 名不升成 ERROR。
不判断引用是否有效。

契约见 codebase_index/NEXT_STEP.md 第 2.3 / 2.4 节。本模块永不抛异常。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from codeindex.scene.lexer import (
    GIT_CONFLICT_MARKERS,
    KNOWN_SECTIONS,
    BlankLine,
    CommentLine,
    GarbageLine,
    HeaderLine,
    Problem,
    PropLine,
    Span,
    Value,
    lex_text,
)

__all__ = [
    "Section",
    "SceneDoc",
    "parse_scene",
    "Problem",
    "Span",
    "Value",
]


@dataclass
class Section:
    """一个 section。props 保序、允许重复键（重复键是真实损坏，dict 会吞掉）。"""

    kind: str
    attrs: dict[str, Value]
    props: list[tuple[str, Value]] = field(default_factory=list)
    span: Span | None = None
    heading_span: Span | None = None


@dataclass
class SceneDoc:
    path: str
    doc_kind: Literal["scene", "resource"]
    format: int | None
    uid: str | None
    script_class: str | None
    sections: list[Section] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)


def _decode_string(raw: str) -> str:
    """把带引号的 raw 字符串解码成内容。只处理 NEXT_STEP 2.2 列出的转义。"""
    if len(raw) < 2 or raw[0] != '"' or raw[-1] != '"':
        return raw
    body = raw[1:-1]
    out: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            if nxt == "n":
                out.append("\n")
            elif nxt == "t":
                out.append("\t")
            elif nxt == "r":
                out.append("\r")
            elif nxt == '"':
                out.append('"')
            elif nxt == "\\":
                out.append("\\")
            elif nxt == "/":
                out.append("/")
            elif nxt == "u" and i + 5 < len(body):
                try:
                    out.append(chr(int(body[i + 2 : i + 6], 16)))
                    i += 6
                    continue
                except ValueError:
                    out.append("\\")
                    out.append("u")
            else:
                out.append("\\")
                out.append(nxt)
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _attr_int(attrs: dict[str, Value], key: str) -> int | None:
    v = attrs.get(key)
    if v is None or v.kind != "int":
        return None
    try:
        return int(v.raw)
    except ValueError:
        return None


def _attr_str(attrs: dict[str, Value], key: str) -> str | None:
    v = attrs.get(key)
    if v is None or v.kind != "str":
        return None
    return _decode_string(v.raw)


def parse_scene(text: str, path: str = "") -> SceneDoc:
    """把 .tscn / .tres 文本收成 SceneDoc。永不抛异常。"""
    result = lex_text(text)
    problems: list[Problem] = list(result.problems)
    sections: list[Section] = []
    doc_kind: Literal["scene", "resource"] = "scene"
    fmt: int | None = None
    uid: str | None = None
    script_class: str | None = None
    seen_first_section = False
    cur: Section | None = None

    for line in result.lines:
        if isinstance(line, (BlankLine, CommentLine)):
            continue
        # Git 冲突标记：按行检测，不管它被词法器归到哪一类
        stripped = text[line.span.byte_start : line.span.byte_end].strip()
        if any(stripped.startswith(m) for m in GIT_CONFLICT_MARKERS):
            problems.append(
                Problem(
                    code="P_GIT_CONFLICT_MARKER",
                    message="发现 Git 冲突标记",
                    span=line.span,
                    stage="parse",
                )
            )
            continue

        if isinstance(line, HeaderLine):
            seen_first_section = True
            if line.name not in KNOWN_SECTIONS:
                problems.append(
                    Problem(
                        code="W_UNKNOWN_SECTION",
                        message=f"未知 section 名 {line.name!r}",
                        span=line.span,
                        stage="parse",
                    )
                )
            cur = Section(
                kind=line.name,
                attrs=line.attrs,
                props=[],
                span=line.span,
                heading_span=line.span,
            )
            sections.append(cur)
            if len(sections) == 1:
                if line.name == "gd_scene":
                    doc_kind = "scene"
                elif line.name == "gd_resource":
                    doc_kind = "resource"
                else:
                    problems.append(
                        Problem(
                            code="P_MISSING_FILE_DESCRIPTOR",
                            message=f"首个 section 是 {line.name!r}，不是 gd_scene / gd_resource",
                            span=line.span,
                            stage="parse",
                        )
                    )
                fmt = _attr_int(line.attrs, "format")
                uid = _attr_str(line.attrs, "uid")
                script_class = _attr_str(line.attrs, "script_class")
            continue

        if isinstance(line, PropLine):
            if not seen_first_section:
                problems.append(
                    Problem(
                        code="P_PROP_BEFORE_SECTION",
                        message="文件描述符之前出现键值",
                        span=line.span,
                        stage="parse",
                    )
                )
                continue
            if cur is not None:
                cur.props.append((line.name, line.value))
                cur.span = Span(
                    cur.span.byte_start,
                    line.span.byte_end,
                    cur.span.line,
                    cur.span.col,
                )
            continue

        if isinstance(line, GarbageLine):
            content = line.text.strip()
            if not content:
                continue
            if not seen_first_section:
                problems.append(
                    Problem(
                        code="P_MISSING_FILE_DESCRIPTOR",
                        message="文件不以 [gd_scene] / [gd_resource] 开头",
                        span=line.span,
                        stage="parse",
                    )
                )
                seen_first_section = True  # 避免整文件刷屏
            elif content.startswith("["):
                problems.append(
                    Problem(
                        code="P_MALFORMED_HEADING",
                        message="[...] 内不是 ident (k=v)*",
                        span=line.span,
                        stage="parse",
                    )
                )
            else:
                problems.append(
                    Problem(
                        code="P_MALFORMED_HEADING",
                        message=f"无法解析的行：{content[:40]!r}",
                        span=line.span,
                        stage="parse",
                    )
                )
            continue

    if not sections and not any(p.code == "P_MISSING_FILE_DESCRIPTOR" for p in problems):
        # 空文件或只有注释/空白
        eof_span = Span(len(text), len(text), 1, 1)
        problems.append(
            Problem(
                code="P_MISSING_FILE_DESCRIPTOR",
                message="文件为空或没有 section",
                span=eof_span,
                stage="parse",
            )
        )

    return SceneDoc(
        path=path,
        doc_kind=doc_kind,
        format=fmt,
        uid=uid,
        script_class=script_class,
        sections=sections,
        problems=problems,
    )
