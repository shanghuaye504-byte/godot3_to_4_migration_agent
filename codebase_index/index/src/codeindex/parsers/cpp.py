"""C++ 解析器。Language 来自 tree-sitter-language-pack.get_language("cpp")。

不写 SQLite。输出 ParseResult。
declarator 会包好几层（pointer / qualified / function_declarator），取函数名必须往里剥。
对照 tests/fixtures/native.cpp 的真实 CST。
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter as ts

from .base import ClassDecl, Edge, ParseResult, Symbol

_LANGUAGE: ts.Language | None = None


def _language() -> ts.Language:
    """懒加载 C++ Language（进程内单例）。"""
    global _LANGUAGE
    if _LANGUAGE is None:
        from tree_sitter_language_pack import get_language

        _LANGUAGE = get_language("cpp")
    return _LANGUAGE


def _slice(source: str, node: ts.Node) -> str:
    return source[node.start_byte : node.end_byte]


def _first_line(source: str, node: ts.Node) -> str:
    return _slice(source, node).splitlines()[0]


class CppParser:
    """无状态。parse() 可并发调用。"""

    def parse(self, path: str, source: str) -> ParseResult:
        """解析单个 .cpp/.h/.hpp。"""
        # CST 根：translation_unit
        #   class_specifier name=PlayerNative  base_class_clause=: public CharacterBody2D
        #     function_definition take_damage（类内定义）
        #     field_declaration hp / die()（原型）
        #   function_definition PlayerNative::die（类外定义）
        #     call_expression queue_free()
        parser = ts.Parser(_language())
        tree = parser.parse(source.encode())
        if tree.root_node.has_error:
            raise SyntaxError(f"cpp parse error in {path}")

        result = ParseResult()
        _walk(tree.root_node, source, result, current_class=None, current_func=None)
        if result.class_decl is None:
            result.class_decl = ClassDecl(Path(path).stem, None, 0)
        return result


def _walk(
    node: ts.Node,
    source: str,
    result: ParseResult,
    current_class: str | None,
    current_func: str | None,
) -> None:
    if node.type == "class_specifier":
        name_node = node.child_by_field_name("name")
        name = _slice(source, name_node) if name_node is not None else "<anon>"
        base = _first_base(node, source)
        if result.class_decl is None:
            result.class_decl = ClassDecl(name, base, node.start_point.row)
        result.symbols.append(
            Symbol(name, "class", node.start_point.row, node.end_point.row, None, None)
        )
        for child in node.children:
            _walk(child, source, result, current_class=name, current_func=None)
        return

    if node.type == "function_definition":
        # CST: function_definition declarator=function_declarator
        #   类内：declarator 里是 field_identifier "take_damage"
        #   类外：declarator 里是 qualified_identifier "PlayerNative::die" → 剥到 name "die"
        # DB:  symbols kind=func；再在 body 里收 call_expression
        declarator = node.child_by_field_name("declarator")
        name = _declarator_name(declarator, source) or "<anon>"
        result.symbols.append(
            Symbol(name, "func", node.start_point.row, node.end_point.row, current_class, _first_line(source, node))
        )
        for child in node.children:
            _walk(child, source, result, current_class, current_func=name)
        return

    if node.type == "field_declaration" and current_class:
        # 两种 field：int hp = 100  → var；void die(); → func 原型
        declarator = node.child_by_field_name("declarator")
        if declarator is not None and declarator.type == "function_declarator":
            name = _declarator_name(declarator, source)
            if name:
                result.symbols.append(
                    Symbol(name, "func", node.start_point.row, node.end_point.row, current_class, _first_line(source, node))
                )
            return
        name = _declarator_name(declarator, source) if declarator is not None else None
        if name:
            result.symbols.append(
                Symbol(name, "var", node.start_point.row, node.end_point.row, current_class, _first_line(source, node))
            )
        return

    if node.type == "call_expression" and current_func:
        # CST: call_expression function=identifier "die" / "queue_free"
        # DB:  edges from_symbol=take_damage to_name="die"
        fn = node.child_by_field_name("function")
        if fn is not None:
            result.edges.append(
                Edge(current_func, _slice(source, fn), node.start_point.row, "call")
            )

    for child in node.children:
        _walk(child, source, result, current_class, current_func)


def _first_base(class_node: ts.Node, source: str) -> str | None:
    # CST: base_class_clause ": public CharacterBody2D"
    #      跳过 access_specifier，取 type_identifier 原文。
    clause = next((c for c in class_node.children if c.type == "base_class_clause"), None)
    if clause is None:
        return None
    ident = next(
        (c for c in clause.children if c.type in ("type_identifier", "qualified_identifier")),
        None,
    )
    return _slice(source, ident) if ident is not None else None


def _declarator_name(node: ts.Node | None, source: str) -> str | None:
    """剥开 function_declarator / pointer / qualified，直到 identifier。

    CST 例子：
      function_declarator
        declarator=field_identifier "take_damage"
      function_declarator
        declarator=qualified_identifier
          name=identifier "die"
    输出：写入 symbols.name 的那一段原文。
    """
    while node is not None:
        if node.type in ("identifier", "field_identifier"):
            return _slice(source, node)
        if node.type == "qualified_identifier":
            name = node.child_by_field_name("name")
            return _slice(source, name) if name is not None else _slice(source, node)
        node = node.child_by_field_name("declarator")
    return None
