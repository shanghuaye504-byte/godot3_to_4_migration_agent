"""场景解析与校验包。

职责、分层和验收见 codebase_index/NEXT_STEP.md。
全部六层已实装：L0 lexer、L1 model、L2 resolve、L3 store、L4 rules、L5 baseline+check。
"""

from codeindex.scene.lexer import (
    BlankLine,
    CommentLine,
    GarbageLine,
    HeaderLine,
    LexResult,
    Line,
    Problem,
    PropLine,
    Span,
    Value,
    lex_text,
)
from codeindex.scene.model import SceneDoc, Section, parse_scene
from codeindex.scene.resolve import (
    Connection,
    ExtRes,
    Ref,
    SceneModel,
    SceneNode,
    SubRes,
    resolve,
)
from codeindex.scene.rules import CheckResult, check_scene
from codeindex.scene.baseline import freeze_baseline, diff_baseline, member_gone_problems
from codeindex.scene.check import scene_check

__all__ = [
    "BlankLine",
    "CommentLine",
    "Connection",
    "ExtRes",
    "GarbageLine",
    "HeaderLine",
    "LexResult",
    "Line",
    "Problem",
    "PropLine",
    "Ref",
    "SceneDoc",
    "SceneModel",
    "SceneNode",
    "Section",
    "Span",
    "SubRes",
    "Value",
    "CheckResult",
    "check_scene",
    "freeze_baseline",
    "diff_baseline",
    "member_gone_problems",
    "scene_check",
    "lex_text",
    "parse_scene",
    "resolve",
]
