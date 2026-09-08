"""GDScript 解析器。Language 来自 tree-sitter-language-pack，不是独立 PyPI 包。

本模块不写 SQLite。唯一产出是 ParseResult（Python 对象），之后由 writer 按下表落库：

    ParseResult.symbols[i]     → INSERT symbols (name, kind, line, end_line, class_name, signature)
    ParseResult.edges[i]       → INSERT edges   (from_symbol, to_name, line, kind)
    ParseResult.class_decl     → INSERT classes (name, base_name, line)   （每文件至多一行）

tree-sitter 给的是 CST（具体语法树）：每个节点有 type、起止字节、子节点。
它不认识「符号表」，只认识「这棵树长什么样」。下面每个函数都在做同一件事：
从某一种 CST 节点上切原文，填进上面三张表对应的 dataclass。
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter as ts

from .base import ClassDecl, Edge, ParseResult, Symbol

_LANGUAGE: ts.Language | None = None


def _language() -> ts.Language:
    """懒加载 GDScript Language（进程内单例）。"""
    # tree-sitter 解析前必须先有一份「这种语言的语法」。Language 就是那份语法
    # 编译后的对象，本身不含任何 .gd 文件内容。
    # 不在这里输出 ParseResult / 不写库；只把 grammar 放到进程里复用。
    global _LANGUAGE
    if _LANGUAGE is None:
        from tree_sitter_language_pack import get_language

        _LANGUAGE = get_language("gdscript")
    return _LANGUAGE


def _slice(source: str, node: ts.Node) -> str:
    """节点对应的源码片段。"""
    # CST 节点不自带字符串，只带 start_byte / end_byte（在 source 这个 UTF-8 文本里的偏移）。
    # 例如 name 节点 [11:17) → "Player"。这就是写入 symbols.name / edges.to_name 的原文。
    return source[node.start_byte : node.end_byte]


def _first_line(source: str, node: ts.Node) -> str:
    """展示用签名：取该语句第一行原文。"""
    # function_definition 整棵子树会一直延伸到函数体结束。库里的 signature 只想要
    # 「func take_damage(amount: int) -> void:」这一行，不要函数体。
    # 对应 symbols.signature，纯展示，不参与 WHERE。
    return _slice(source, node).splitlines()[0]


class GdscriptParser:
    """无状态。parse() 可并发调用（Language 是只读单例）。"""

    def parse(self, path: str, source: str) -> ParseResult:
        """解析单个 .gd 文件。root.has_error 时抛 SyntaxError，让 writer 记 failed。"""
        # ---------- 1) CST ----------
        # Parser.parse(bytes) 得到一棵树。根节点 type=source，children 是文件顶层语句。
        # player.gd 的根大致是：
        #   source
        #     class_name_statement    "class_name Player"
        #     extends_statement       "extends CharacterBody2D"
        #     signal_statement        "signal died"
        #     const_statement         "const MAX_HP := 100"
        #     variable_statement      "var hp := MAX_HP"
        #     function_definition     take_damage
        #     function_definition     _die
        # 未命名子节点（换行、注释）用 is_named 滤掉。
        parser = ts.Parser(_language())
        tree = parser.parse(source.encode())
        if tree.root_node.has_error:
            # 语法残缺时 tree-sitter 仍会产出一棵带 error 节点的树。
            # 约定：整文件作废，不返回半套符号（writer 会保留 files 行、清空子表）。
            raise SyntaxError(f"gdscript parse error in {path}")

        # ---------- 2) 空的「三表」容器 ----------
        # 还不是 SQL 行，只是和 schema 字段一一对应的 dataclass。
        result = ParseResult()
        default_class = Path(path).stem  # 没有 class_name 时用文件名，如 player
        current_class: str | None = None
        extends_from_top: str | None = None
        extends_line = 0

        # ---------- 3) 按顶层节点 type 分流，填进 result ----------
        for node in tree.root_node.children:
            if not node.is_named:
                continue
            kind = node.type

            if kind == "class_name_statement":
                # CST: class_name_statement → 字段 name="Player"
                # DB:  symbols 一行 kind=class；同时记住名字，后面拼 class_decl
                name = _slice(source, node.child_by_field_name("name"))
                current_class = name
                result.symbols.append(
                    Symbol(name, "class", node.start_point.row, node.end_point.row, None, _first_line(source, node))
                )
            elif kind == "extends_statement":
                # CST: 独立一句，不挂在 class_name 下面
                # DB:  不单独进 symbols；base_name 留给最后的 ClassDecl → classes 表
                extends_from_top = _extends_name(source, node)
                extends_line = node.start_point.row
            elif kind == "class_definition":
                # CST: `class Inner:` 内嵌类（和文件级 class_name 不是同一种节点）
                _walk_class_definition(node, source, result, default_class)
            elif kind == "function_definition":
                # CST: func 名 + parameters + body（body 里还有 call）
                # DB:  symbols kind=func 一行 + edges 若干行
                _add_function(node, source, result, current_class)
            elif kind == "signal_statement":
                _add_named(node, source, result, "signal", current_class)
            elif kind == "variable_statement":
                _add_named(node, source, result, "var", current_class)
            elif kind == "const_statement":
                _add_named(node, source, result, "const", current_class)
            elif kind == "enum_definition":
                _add_named(node, source, result, "enum", current_class)

        # ---------- 4) 两句 CST 合成 classes 表需要的一行 ----------
        # class_name Player + extends CharacterBody2D → ClassDecl(Player, CharacterBody2D, line)
        # writer 之后：INSERT classes (name, base_name, line)
        class_name = current_class or default_class
        if current_class is not None or extends_from_top is not None:
            result.class_decl = ClassDecl(
                name=class_name,
                base_name=extends_from_top,
                line=extends_line if extends_from_top is not None else 0,
            )

        # ---------- 5) 本函数的输出 ----------
        # ParseResult(symbols=[...], edges=[...], class_decl=ClassDecl|None)
        # 调用方（writer）负责开事务写入；这里保证 to_name/base_name 已是原文。
        return result


def _extends_name(source: str, node: ts.Node) -> str | None:
    """extends_statement 的基类原文。"""
    # CST（player.gd 第 2 行）：
    #   extends_statement
    #     [未命名] "extends"     关键字，is_named=False
    #     type "CharacterBody2D"  基类，没有 field name，只能按 type=="type" 找
    # 转化：切出原文 "CharacterBody2D"
    # 输出：str | None，由 parse() 写入 ClassDecl.base_name → classes.base_name
    #       引擎类在 symbols 里往往没有对应行，这是故意的（查询期字符串对不上就停）。
    type_node = next((c for c in node.children if c.is_named and c.type == "type"), None)
    if type_node is None:
        return None
    return _slice(source, type_node)


def _add_named(node: ts.Node, source: str, result: ParseResult, kind: str, class_name: str | None) -> None:
    # CST：signal / var / const / enum 都带字段 name，形状类似
    #   const_statement
    #     name "MAX_HP"
    #     type / value ...     （本函数不用，索引不存初值）
    # 转化：name 原文 + 调用方传入的 kind（signal/var/const/enum）
    # 输出：往 result.symbols 追加一条 Symbol
    #   → writer INSERT symbols (name, kind, line, end_line, class_name, signature)
    #   class_name 是所属类（文件级 Player 或内嵌类名），顶层且没有 class_name 时为 None
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    result.symbols.append(
        Symbol(
            _slice(source, name_node),
            kind,
            node.start_point.row,
            node.end_point.row,
            class_name,
            _first_line(source, node),
        )
    )


def _add_function(node: ts.Node, source: str, result: ParseResult, class_name: str | None) -> None:
    # CST：
    #   function_definition
    #     name "take_damage"
    #     parameters "(amount: int)"
    #     return_type "void"
    #     body
    #       ... call / attribute ...
    # 转化成库里的两样东西：
    #   1) symbols 一行 kind=func（定义位置，给 find-symbol）
    #   2) 函数体里每次调用 → edges 一行（给 call-chain；from_symbol=本函数名）
    name_node = node.child_by_field_name("name")
    name = _slice(source, name_node) if name_node is not None else "<anonymous>"
    result.symbols.append(
        Symbol(name, "func", node.start_point.row, node.end_point.row, class_name, _first_line(source, node))
    )
    result.edges.extend(_call_edges(node, source, name))


def _walk_class_definition(node: ts.Node, source: str, result: ParseResult, fallback: str) -> None:
    """`class Inner:` 这种内嵌类。每文件主 class_decl 仍以文件级 class_name 为准。"""
    # CST：class_definition 和文件头的 class_name_statement 不是同一种节点
    #   class_definition
    #     name "Inner"
    #     class_body
    #       function_definition / variable_statement / ...
    # 转化：Inner 进 symbols(kind=class)；body 里的成员 class_name 填 Inner
    # 输出：只追加 symbols/edges，不覆盖 result.class_decl
    #       （主继承链仍是文件级 Player extends CharacterBody2D → classes 表那一行）
    name_node = node.child_by_field_name("name")
    inner = _slice(source, name_node) if name_node is not None else fallback
    result.symbols.append(
        Symbol(inner, "class", node.start_point.row, node.end_point.row, None, _first_line(source, node))
    )
    body = next((c for c in node.children if c.type == "class_body"), None)
    if body is None:
        return
    for child in body.children:
        if not child.is_named:
            continue
        if child.type == "function_definition":
            _add_function(child, source, result, inner)
        elif child.type == "variable_statement":
            _add_named(child, source, result, "var", inner)
        elif child.type == "const_statement":
            _add_named(child, source, result, "const", inner)
        elif child.type == "signal_statement":
            _add_named(child, source, result, "signal", inner)


def _call_edges(func_node: ts.Node, source: str, func_name: str) -> list[Edge]:
    """收集函数体内的调用，变成 edges 表的行。"""
    # 从 function_definition 整棵子树 DFS。两种 CST 都算「一次调用」：
    #
    # A) type=call                    _die() / queue_free() / preload("x")
    #      identifier "_die"
    #      arguments  "()"
    #    转化：to_name = identifier 原文；preload 则 kind=preload，否则 call
    #
    # B) type=attribute 且含 attribute_call     died.emit()
    #      identifier "died"
    #      "."
    #      attribute_call
    #        identifier "emit"
    #        arguments "()"
    #    转化：to_name = 从 attribute 开头切到 arguments 之前 → "died.emit"
    #         （整段 attribute 原文是 "died.emit()"，库里不要括号）
    #
    # 输出：list[Edge]，每条对应 INSERT edges (from_symbol, to_name, line, kind)
    #   from_symbol = 当前函数名（调用方）
    #   to_name     = 源码原文（被调方，不绑 symbols.id）
    edges: list[Edge] = []
    stack = [func_node]
    while stack:
        node = stack.pop()
        if node.type == "call":
            callee = next(
                (c for c in node.children if c.is_named and c.type != "arguments"),
                None,
            )
            if callee is not None:
                to_name = _slice(source, callee)
                kind = "preload" if to_name == "preload" else "call"
                edges.append(Edge(func_name, to_name, node.start_point.row, kind))
        elif node.type == "attribute" and _has_child_type(node, "attribute_call"):
            ac = next(c for c in node.children if c.type == "attribute_call")
            args = next((c for c in ac.children if c.type == "arguments"), None)
            end = args.start_byte if args is not None else ac.end_byte
            to_name = source[node.start_byte : end].rstrip()
            edges.append(Edge(func_name, to_name, node.start_point.row, "call"))
        stack.extend(node.children)
    return edges


def _has_child_type(node: ts.Node, type_name: str) -> bool:
    # CST 工具：判断节点的直接子节点里有没有某种 type。
    # 用来区分「普通属性访问 obj.hp」和「带调用的属性 died.emit()」——
    # 后者才有 attribute_call 子节点，才应该变成 edges 一行。
    return any(c.type == type_name for c in node.children)
