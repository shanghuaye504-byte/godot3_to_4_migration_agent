"""Parse ``renames_map_3_to_4.cpp`` → ``build/intermediate/renames.jsonl``.

Pure regex, one pass. C# arrays are skipped on purpose (GDScript-only).
Commented-out entries are kept with ``source=official_renames_skipped``.
``{ nullptr, nullptr }`` sentinels are recognized and do not count as
unrecognized lines. Any other unmatched line inside an array fails the build.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

_BUILD_DIR = Path(__file__).resolve().parent
if str(_BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(_BUILD_DIR))

from _util import INTERMEDIATE, OFFICIAL, make_id, write_jsonl, write_report_json  # noqa: E402
from rag.retriever.schemas import (  # noqa: E402
    AgentAction,
    ChangeKind,
    DetectionMethod,
    MigrationRule,
    SymbolKind,
)

ARRAY_START = re.compile(r"RenamesMap3To4::(\w+)\[\]\[2\]\s*=\s*\{")
ENTRY = re.compile(
    r'^\s*(?P<commented>//\s*)?\{\s*"(?P<old>(?:[^"\\]|\\.)*)"\s*,\s*"(?P<new>(?:[^"\\]|\\.)*)"\s*\}\s*,?'
    r"\s*(?://\s*(?P<comment>.*))?$"
)
NULL_SENTINEL = re.compile(r"^\s*\{\s*nullptr\s*,\s*nullptr\s*\}\s*,?\s*$")
ARRAY_END = re.compile(r"^\s*\};\s*$")
COMMENT_OR_BLANK = re.compile(r"^\s*(//.*)?$")

ARRAY_TO_KIND: dict[str, SymbolKind] = {
    "class_renames": SymbolKind.class_,
    "gdscript_function_renames": SymbolKind.method,
    "gdscript_properties_renames": SymbolKind.property,
    "gdscript_signals_renames": SymbolKind.signal,
    "enum_renames": SymbolKind.enum,
    "project_settings_renames": SymbolKind.project_setting,
    "project_godot_renames": SymbolKind.project_setting,
    "input_map_renames": SymbolKind.project_setting,
    "builtin_types_renames": SymbolKind.builtin,
    "shaders_renames": SymbolKind.shader,
    "color_renames": SymbolKind.color,
    "theme_override_renames": SymbolKind.theme,
}

CSHARP_PREFIX = "csharp_"
SINCE = "4.0"


def parse_cpp(text: str) -> tuple[list[MigrationRule], dict]:
    rules: list[MigrationRule] = []
    per_array: dict[str, dict[str, int]] = defaultdict(lambda: {"enabled": 0, "skipped": 0})
    unrecognized: list[tuple[int, str]] = []
    csharp_skipped_arrays: list[str] = []

    current: str | None = None
    skipping_csharp = False
    kind: SymbolKind | None = None

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip("\n")

        if current is None and not skipping_csharp:
            m = ARRAY_START.search(line)
            if not m:
                continue
            name = m.group(1)
            if name.startswith(CSHARP_PREFIX):
                skipping_csharp = True
                current = name
                csharp_skipped_arrays.append(name)
                continue
            if name not in ARRAY_TO_KIND:
                unrecognized.append((lineno, line))
                current = name
                kind = None
                continue
            current = name
            kind = ARRAY_TO_KIND[name]
            continue

        if skipping_csharp:
            if ARRAY_END.match(line):
                skipping_csharp = False
                current = None
            continue

        if ARRAY_END.match(line):
            current = None
            kind = None
            continue
        if NULL_SENTINEL.match(line):
            continue

        em = ENTRY.match(line)
        if em and kind is not None:
            old, new = em.group("old"), em.group("new")
            comment = (em.group("comment") or "").strip() or None
            commented = bool(em.group("commented"))
            if commented:
                source = "official_renames_skipped"
                converter_gap = True
                agent_action = AgentAction.apply_and_warn
                per_array[current]["skipped"] += 1
            else:
                source = "official_renames"
                converter_gap = False
                agent_action = AgentAction.apply_rename
                per_array[current]["enabled"] += 1

            payload: dict = {"cpp_array": current}
            if comment:
                payload["cpp_comment"] = comment

            rules.append(
                MigrationRule(
                    id=make_id(source, SINCE, None, kind.value, old, extra=new if commented else None),
                    old_symbol=old,
                    new_symbol=new,
                    owner=None,
                    symbol_kind=kind,
                    change=ChangeKind.rename,
                    match_tokens=[old, new],
                    since_version=SINCE,
                    detection_method=DetectionMethod.agent_retrieval,
                    converter_gap=converter_gap,
                    agent_action=agent_action,
                    source=source,
                    payload=payload,
                )
            )
            continue

        if COMMENT_OR_BLANK.match(line):
            continue
        unrecognized.append((lineno, line))

    report = {
        "per_array": dict(per_array),
        "csharp_skipped_arrays": csharp_skipped_arrays,
        "unrecognized": [{"line": n, "text": t} for n, t in unrecognized],
        "unrecognized_count": len(unrecognized),
        "rule_count": len(rules),
    }
    return rules, report


def main() -> int:
    src = OFFICIAL / "renames_map_3_to_4.cpp"
    rules, report = parse_cpp(src.read_text(encoding="utf-8"))
    out = INTERMEDIATE / "renames.jsonl"
    n = write_jsonl(out, rules)
    write_report_json("renames", report)

    print(f"parse_renames_cpp: wrote {n} rows → {out}")
    for name, counts in report["per_array"].items():
        print(f"  {name}: enabled={counts['enabled']} skipped={counts['skipped']}")
    print(f"  csharp arrays skipped: {report['csharp_skipped_arrays']}")
    print(f"  unrecognized lines: {report['unrecognized_count']}")
    if report["unrecognized"]:
        for item in report["unrecognized"]:
            print(f"    L{item['line']}: {item['text']}", file=sys.stderr)
        print(
            "Unrecognized lines inside arrays. If the count jumped, check for "
            "`//` inside a symbol string (Godot naming should never do this).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
