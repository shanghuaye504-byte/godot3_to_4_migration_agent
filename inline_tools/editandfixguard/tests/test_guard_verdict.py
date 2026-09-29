"""Step 8 裁决的验收测试。

验收条目见 NEXT_STEP.md「Step 8 裁决」。测试直接调用
`inline_tools.editandfixguard.guard.verdict`，喂给它各判据的真实 Result
对象。本步不落盘。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _import(name: str):
    sys.path.insert(0, str(REPO_ROOT))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(REPO_ROOT))


guard = _import("inline_tools.editandfixguard.guard")
symbols = _import("inline_tools.editandfixguard.symbols")
scene_names = _import("inline_tools.editandfixguard.scene_names")

GuardResult = guard.GuardResult
GuardViolation = guard.GuardViolation
verdict = guard.verdict


def _guard_result(*violations: GuardViolation, overrides: list[str] | None = None) -> GuardResult:
    result = GuardResult()
    result.violations.extend(violations)
    if overrides:
        result.overrides.extend(overrides)
    return result


class TestVerdictRule:
    """任一 block 未被其 override 接住 → reject；只有 warn → warn；否则 pass。"""

    def test_block_without_override_is_reject(self) -> None:
        result = _guard_result(GuardViolation(id="X", file="f", line=1, message="m", block=True))
        out = verdict(result)
        assert out["verdict"] == "reject"

    def test_block_caught_by_override_is_not_reject(self) -> None:
        result = _guard_result(
            GuardViolation(id=guard.BULK_DELETE, file="f", line=None, message="m", block=True),
            overrides=[guard.BULK_DELETE],
        )
        out = verdict(result)
        assert out["verdict"] != "reject"

    def test_only_warn_is_warn(self) -> None:
        result = _guard_result(GuardViolation(id="W", file="f", line=None, message="m", block=False))
        out = verdict(result)
        assert out["verdict"] == "warn"

    def test_clean_is_pass(self) -> None:
        out = verdict(_guard_result())
        assert out["verdict"] == "pass"


class TestRejectKeepsWarns:
    """reject 时同一次调用里的 warn 仍出现在 violations 里。"""

    def test_reject_keeps_warn_entries(self) -> None:
        result = _guard_result(
            GuardViolation(id="B", file="f", line=1, message="block", block=True),
            GuardViolation(id="W", file="f", line=2, message="warn", block=False),
        )
        out = verdict(result)
        assert out["verdict"] == "reject"
        ids = [v["id"] for v in out["violations"]]
        assert "B" in ids and "W" in ids


class TestViolationShape:
    """violations 含 id、file、line、message；锚点失败另附候选片段。"""

    def test_violation_keys(self) -> None:
        result = _guard_result(GuardViolation(id="X", file="res://f.gd", line=3, message="m", block=True))
        out = verdict(result)
        entry = out["violations"][0]
        assert entry["id"] == "X"
        assert entry["file"] == "res://f.gd"
        assert entry["line"] == 3
        assert entry["message"] == "m"

    def test_anchor_error_carries_candidates(self) -> None:
        anchor_error = {
            "code": "ANCHOR_NOT_FOUND",
            "message": "anchor not found",
            "candidates": [{"line": 5, "ratio": 0.8, "snippet": ["x"]}],
        }
        out = verdict(anchor_error=anchor_error)
        assert out["verdict"] == "reject"
        entry = out["violations"][0]
        assert entry["candidates"] == anchor_error["candidates"]


class TestOverrideInJson:
    """override 进入返回 JSON。"""

    def test_overrides_in_output(self) -> None:
        result = _guard_result(
            GuardViolation(id=guard.BULK_DELETE, file="f", line=None, message="m", block=True),
            overrides=[guard.BULK_DELETE],
        )
        out = verdict(result)
        assert guard.BULK_DELETE in out["overrides"]


class TestCountsAsVerifyRound:
    """reject → false；pass 与 warn → true。"""

    def test_reject_not_counted(self) -> None:
        out = verdict(_guard_result(GuardViolation(id="B", file="f", line=1, message="m", block=True)))
        assert out["counts_as_verify_round"] is False

    def test_pass_counted(self) -> None:
        assert verdict(_guard_result())["counts_as_verify_round"] is True

    def test_warn_counted(self) -> None:
        out = verdict(_guard_result(GuardViolation(id="W", file="f", line=None, message="m", block=False)))
        assert out["counts_as_verify_round"] is True


class TestFuzzyAnchor:
    """FUZZY_ANCHOR 不单独构成 reject；没有 block 时 verdict 至少是 warn。"""

    def test_fuzzy_alone_is_warn_not_reject(self) -> None:
        out = verdict(_guard_result(), anchor_warnings=["FUZZY_ANCHOR: line 5 ratio 0.950"])
        assert out["verdict"] == "warn"
        assert out["counts_as_verify_round"] is True

    def test_fuzzy_plus_clean_is_at_least_warn(self) -> None:
        out = verdict(anchor_warnings=["FUZZY_ANCHOR: line 3 ratio 0.930"])
        assert out["verdict"] == "warn"

    def test_fuzzy_does_not_block(self) -> None:
        # fuzzy + 一个被 override 接住的 block：fuzzy 不把 warn 抬成 reject
        result = _guard_result(
            GuardViolation(id=guard.BULK_DELETE, file="f", line=None, message="m", block=True),
            overrides=[guard.BULK_DELETE],
        )
        out = verdict(result, anchor_warnings=["FUZZY_ANCHOR: line 1 ratio 0.925"])
        assert out["verdict"] == "warn"


class TestCrossCriterionResults:
    """verdict 能吃三种判据的 Result 对象（GuardResult / SymbolCheckResult / SceneCheckResult）。"""

    def test_mixed_results(self) -> None:
        g = _guard_result(GuardViolation(id="W", file="f", line=None, message="w", block=False))
        sym = symbols.SymbolCheckResult()
        sc = scene_names.SceneCheckResult()
        out = verdict(g, sym, sc)
        assert out["verdict"] == "warn"

    def test_symbol_block_rejects(self) -> None:
        sym = symbols.SymbolCheckResult()
        sym.violations.append(symbols.SymbolViolation(
            id=symbols.SYMBOL_REMOVED, file="f", symbol="x", message="m",
        ))
        out = verdict(sym)
        assert out["verdict"] == "reject"
