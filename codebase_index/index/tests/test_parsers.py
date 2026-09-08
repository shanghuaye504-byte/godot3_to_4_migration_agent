"""每个 parser 单独测（不需要起 daemon）：直接对 fixtures 喂源码。"""

from pathlib import Path

import pytest

from codeindex.parsers.cpp import CppParser
from codeindex.parsers.csharp import CSharpParser
from codeindex.parsers.gdscript import GdscriptParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_gdscript_symbols_and_edges():
    result = GdscriptParser().parse("player.gd", (FIXTURES / "player.gd").read_text())

    names = {s.name: s.kind for s in result.symbols}
    assert names["Player"] == "class"
    assert names["take_damage"] == "func"
    assert names["_die"] == "func"
    assert names["died"] == "signal"
    assert names["MAX_HP"] == "const"
    assert names["hp"] == "var"

    assert result.class_decl is not None
    assert result.class_decl.name == "Player"
    assert result.class_decl.base_name == "CharacterBody2D"

    calls = {(e.from_symbol, e.to_name) for e in result.edges if e.kind == "call"}
    assert ("take_damage", "_die") in calls
    assert ("_die", "queue_free") in calls
    assert ("_die", "died.emit") in calls


def test_gdscript_syntax_error_raises():
    with pytest.raises(SyntaxError):
        GdscriptParser().parse("broken.gd", "func broken(:\n")


def test_csharp_symbols_and_edges():
    result = CSharpParser().parse("Player.cs", (FIXTURES / "Player.cs").read_text())

    names = {s.name: s.kind for s in result.symbols}
    assert names["Player"] == "class"
    assert names["TakeDamage"] == "func"
    assert names["Die"] == "func"
    assert names["Hp"] == "var"

    assert result.class_decl is not None
    assert result.class_decl.name == "Player"
    assert result.class_decl.base_name == "CharacterBody2D"

    calls = {(e.from_symbol, e.to_name) for e in result.edges}
    assert ("TakeDamage", "Die") in calls
    assert ("Die", "QueueFree") in calls


def test_csharp_syntax_error_raises():
    with pytest.raises(SyntaxError):
        CSharpParser().parse("broken.cs", "class X { void F( ")


def test_cpp_symbols_and_edges():
    result = CppParser().parse("native.cpp", (FIXTURES / "native.cpp").read_text())

    names = {s.name: s.kind for s in result.symbols}
    assert names["PlayerNative"] == "class"
    assert names["take_damage"] == "func"
    assert names["die"] == "func"
    assert names["hp"] == "var"

    assert result.class_decl is not None
    assert result.class_decl.name == "PlayerNative"
    assert result.class_decl.base_name == "CharacterBody2D"

    calls = {(e.from_symbol, e.to_name) for e in result.edges}
    assert ("take_damage", "die") in calls
    assert ("die", "queue_free") in calls


def test_cpp_syntax_error_raises():
    with pytest.raises(SyntaxError):
        CppParser().parse("broken.cpp", "void foo( {")
