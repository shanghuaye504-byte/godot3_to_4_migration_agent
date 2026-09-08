"""C# 解析器。Language 来自 tree-sitter-language-pack.get_language("csharp")。

不写 SQLite。输出 ParseResult，由 writer 落库（与 gdscript.py 同一套 dataclass）。
对照 tests/fixtures/Player.cs 的真实 CST，不是骨架里猜的节点名。
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter as ts

from .base import ClassDecl, Edge, ParseResult, Symbol

_LANGUAGE: ts.Language | None = None


def _language() -> ts.Language:
    """懒加载 C# Language（进程内单例）。"""
    global _LANGUAGE
    if _LANGUAGE is None:
        from tree_sitter_language_pack import get_language

        _LANGUAGE = get_language("csharp")
    return _LANGUAGE


def _slice(source: str, node: ts.Node) -> str:
    return source[node.start_byte : node.end_byte]


def _first_line(source: str, node: ts.Node) -> str:
    return _slice(source, node).splitlines()[0]


class CSharpParser:
    """无状态。parse() 可并发调用。"""

    def parse(self, path: str, source: str) -> ParseResult:
        """解析单个 .cs 文件。base_list 只取第一个基类。"""
        # CST 根：compilation_unit
        #   using_directive
        #   class_declaration  name=Player  base_list=: CharacterBody2D
        #     declaration_list
        #       field_declaration     Hp
        #       method_declaration    TakeDamage / Die
        #         body 里 invocation_expression  Die() / QueueFree()
        parser = ts.Parser(_language())
        tree = parser.parse(source.encode())
        if tree.root_node.has_error:
            raise SyntaxError(f"csharp parse error in {path}")

        result = ParseResult()
        _walk(tree.root_node, source, result, current_class=None, current_method=None)
        if result.class_decl is None:
            result.class_decl = ClassDecl(Path(path).stem, None, 0)
        return result


def _walk(
    node: ts.Node,
    source: str,
    result: ParseResult,
    current_class: str | None,
    current_method: str | None,
) -> None:
    # 深度优先。遇到 class / method / field 就抽符号；
    # 在某个 method 内部遇到 invocation_expression 就抽边（from=当前方法名）。
    if node.type == "class_declaration":
        name_node = node.child_by_field_name("name")
        name = _slice(source, name_node) if name_node is not None else "<anon>"
        base = _first_base(node, source)
        if result.class_decl is None:
            # 第一份 class → classes 表那一行（Player, CharacterBody2D）
            result.class_decl = ClassDecl(name, base, node.start_point.row)
        result.symbols.append(
            Symbol(name, "class", node.start_point.row, node.end_point.row, None, None)
        )
        for child in node.children:
            _walk(child, source, result, current_class=name, current_method=None)
        return

    if node.type == "method_declaration":
        name_node = node.child_by_field_name("name")
        name = _slice(source, name_node) if name_node is not None else "<anon>"
        # CST: method_declaration name=identifier parameters=parameter_list body=block
        # DB:  symbols kind=func
        result.symbols.append(
            Symbol(name, "func", node.start_point.row, node.end_point.row, current_class, _first_line(source, node))
        )
        for child in node.children:
            _walk(child, source, result, current_class, current_method=name)
        return

    if node.type == "field_declaration":
        # CST: field_declaration → variable_declaration → variable_declarator name=Hp
        # DB:  symbols kind=var
        decl = next((c for c in node.children if c.type == "variable_declaration"), None)
        if decl is not None:
            for child in decl.children:
                if child.type == "variable_declarator":
                    n = child.child_by_field_name("name")
                    if n is not None:
                        result.symbols.append(
                            Symbol(
                                _slice(source, n),
                                "var",
                                node.start_point.row,
                                node.end_point.row,
                                current_class,
                                _first_line(source, node),
                            )
                        )
        return

    if node.type == "invocation_expression" and current_method:
        # CST: invocation_expression function=identifier "Die"  arguments="()"
        # DB:  edges from_symbol=TakeDamage to_name="Die" kind=call
        fn = node.child_by_field_name("function")
        if fn is not None:
            result.edges.append(
                Edge(current_method, _slice(source, fn), node.start_point.row, "call")
            )

    for child in node.children:
        _walk(child, source, result, current_class, current_method)


def _first_base(class_node: ts.Node, source: str) -> str | None:
    # CST: base_list → ": CharacterBody2D"，第一个 identifier 就是基类原文。
    # DB:  ClassDecl.base_name → classes.base_name
    base_list = next((c for c in class_node.children if c.type == "base_list"), None)
    if base_list is None:
        return None
    ident = next((c for c in base_list.children if c.is_named), None)
    return _slice(source, ident) if ident is not None else None
