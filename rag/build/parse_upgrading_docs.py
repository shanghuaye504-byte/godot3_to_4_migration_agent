"""Parse 4.1–4.7 upgrading rst (+ 3→4 shader prose carve-out).

Structured table rows → ``build/intermediate/rst_4x.jsonl``.
Unstructured paragraphs → ``vault/tier_b_prose/<stem>.prose.jsonl``.
``upgrading_to_godot_4.rst`` is copied to ``artifacts/agent_context/``; only
the ``Updating shaders`` section is extracted as prose (no table/regex rows).
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_BUILD_DIR = Path(__file__).resolve().parent
if str(_BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(_BUILD_DIR))

from _util import (  # noqa: E402
    ARTIFACTS,
    INTERMEDIATE,
    MANUAL,
    OFFICIAL,
    PROSE_DIR,
    load_manifest,
    make_id,
    write_jsonl,
    write_report_json,
)
from rag.retriever.schemas import (  # noqa: E402
    AgentAction,
    ChangeKind,
    DetectionMethod,
    MigrationRule,
    SymbolKind,
)
from rag.version_codec import version_to_code  # noqa: E402

from docutils.nodes import (  # noqa: E402
    NodeVisitor,
    SkipNode,
    admonition,
    entry,
    literal,
    literal_block,
    paragraph,
    row,
    section,
    table,
    tbody,
    thead,
    title,
)
from docutils.parsers.rst import Parser  # noqa: E402
from docutils.utils import new_document  # noqa: E402

PROSE_MIN_CHARS = 40
SINCE_RE = re.compile(r"^upgrading_to_godot_4\.(\d+)\.rst$")
GH_RE = re.compile(r"GH-(\d+)")
SUBST_USE_RE = re.compile(r"\|([^|\n]{1,60})\|")
EXISTING_SUBST_NAME_RE = re.compile(r"^\.\.\s+\|([^|]+)\|", re.M)

KIND_PREFIXES: list[tuple[str, SymbolKind]] = [
    ("Method", SymbolKind.method),
    ("Property", SymbolKind.property),
    ("Signal", SymbolKind.signal),
    ("Constant", SymbolKind.constant),
    ("Enum", SymbolKind.enum),
    ("Type", SymbolKind.class_),
    ("Class", SymbolKind.class_),
    ("Member", SymbolKind.property),
    ("Parameter", SymbolKind.property),
]

REMOVED_RE = re.compile(r"\bremoved\b", re.I)
RENAMED_RE = re.compile(r"renamed to", re.I)
REPLACED_RE = re.compile(r"replaced (?:with|by)", re.I)
SPLIT_RE = re.compile(r"split into", re.I)
ADDS_PARAM_RE = re.compile(r"adds?\b.+\bparameters?\b", re.I)
CHANGES_RETURN_RE = re.compile(r"changes return type from", re.I)
CHANGES_TYPE_RE = re.compile(
    r"changes(?:\s+\w+)*\s+type(?:\s+metadata)?\s+from", re.I
)
CHANGES_VALUE_RE = re.compile(r"changes value from", re.I)
CHANGES_INHERIT_RE = re.compile(r"changes inheritance from", re.I)
MOVED_RE = re.compile(r"moved to (?:the\s+)?(?:base\s+)?(?:class|enum)", re.I)
REMOVES_PARAM_RE = re.compile(r"removes?\s+.+\s+parameter", re.I)
ADDED_RE = re.compile(r"\badded\b", re.I)


def inject_substitution_defs(rst_text: str) -> str:
    existing = set(EXISTING_SUBST_NAME_RE.findall(rst_text))
    names = sorted(set(SUBST_USE_RE.findall(rst_text)))
    missing = [n for n in names if n not in existing]
    if not missing:
        return rst_text
    preamble = "\n".join(f".. |{n}| replace:: {n}" for n in missing)
    return preamble + "\n\n" + rst_text


def parse_doctree(rst_text: str, source_path: str):
    try:
        from docutils.frontend import get_default_settings

        settings = get_default_settings(Parser)
    except Exception:  # pragma: no cover - older docutils
        from docutils.frontend import OptionParser

        settings = OptionParser(components=(Parser,)).get_default_values()
    settings.report_level = 5
    settings.halt_level = 5
    document = new_document(source_path, settings)
    Parser().parse(rst_text, document)
    return document


def _section_title(node) -> str:
    for child in node.children:
        if isinstance(child, title):
            return child.astext().strip()
    return ""


def _literals(node) -> list[str]:
    return [n.astext() for n in node.findall(literal)]


def _cell_entries(r: row) -> list:
    return [c for c in r.children if isinstance(c, entry)]


def _compat_bool(text: str) -> bool | None:
    t = text.strip()
    if not t or t.upper() == "N/A":
        return None
    if "❌" in t:
        return False
    if "✔️" in t or "✔" in t:
        return True
    return None


def _symbol_kind_from_text(text: str) -> SymbolKind:
    for prefix, kind in KIND_PREFIXES:
        if text.startswith(prefix) or text.lower().startswith(prefix.lower()):
            return kind
    return SymbolKind.method


def _classify(text: str, literals: list[str], kind: SymbolKind) -> dict[str, Any]:
    """Return change / symbols / extra / classified flag."""
    first = literals[0] if literals else None
    second = literals[1] if len(literals) > 1 else None

    if REMOVED_RE.search(text) and not REMOVES_PARAM_RE.search(text):
        return {
            "change": ChangeKind.remove,
            "old": first,
            "new": None,
            "extra": None,
            "classified": True,
        }
    if RENAMED_RE.search(text):
        return {
            "change": ChangeKind.rename,
            "old": first,
            "new": second,
            "extra": second,
            "classified": True,
        }
    if REPLACED_RE.search(text):
        return {
            "change": ChangeKind.replace,
            "old": first,
            "new": second,
            "extra": second,
            "classified": True,
        }
    if SPLIT_RE.search(text):
        return {
            "change": ChangeKind.split,
            "old": first,
            "new": None,
            "extra": second,
            "classified": True,
            "extra_tokens": literals[1:],
        }
    if ADDS_PARAM_RE.search(text) or REMOVES_PARAM_RE.search(text):
        return {
            "change": ChangeKind.signature,
            "old": first,
            "new": first,
            "extra": second,
            "classified": True,
        }
    if CHANGES_RETURN_RE.search(text):
        return {
            "change": ChangeKind.signature if kind == SymbolKind.method else ChangeKind.type,
            "old": first,
            "new": first,
            "extra": None,
            "classified": True,
        }
    if CHANGES_TYPE_RE.search(text):
        change = ChangeKind.signature if kind == SymbolKind.method else ChangeKind.type
        return {
            "change": change,
            "old": first,
            "new": first,
            "extra": None,
            "classified": True,
        }
    if CHANGES_INHERIT_RE.search(text):
        return {
            "change": ChangeKind.type,
            "old": first,
            "new": first,
            "extra": second,
            "classified": True,
        }
    if CHANGES_VALUE_RE.search(text):
        return {
            "change": ChangeKind.default,
            "old": first,
            "new": first,
            "extra": first,
            "classified": True,
        }
    if MOVED_RE.search(text):
        moved_to = literals[-1] if literals else None
        return {
            "change": ChangeKind.move,
            "old": first,
            "new": first,
            "extra": moved_to,
            "classified": True,
            "moved_to": moved_to,
        }
    if ADDED_RE.search(text) and not ADDS_PARAM_RE.search(text):
        return {
            "change": ChangeKind.add,
            "old": None,
            "new": first,
            "extra": first,
            "classified": True,
        }
    return {
        "change": ChangeKind.behavior,
        "old": first,
        "new": first,
        "extra": second or first,
        "classified": False,
    }


def _header_key(text: str) -> str | None:
    n = re.sub(r"\s+", " ", text).strip().lower()
    if n in {"change", "member", "property/parameter", "property / parameter"}:
        return "change"
    if "gdscript" in n:
        return "gdscript"
    if "binary" in n and "c#" in n:
        return "csharp_binary"
    if "source" in n and "c#" in n:
        return "csharp_source"
    if n == "introduced":
        return "introduced"
    if n.startswith("old "):
        return "old_default"
    if n.startswith("new "):
        return "new_default"
    return None


def _is_owner_row(cells: list[tuple[str, list[str]]]) -> bool:
    if not cells:
        return False
    first_text = cells[0][0].strip()
    if not first_text:
        return False
    return all(not c[0].strip() for c in cells[1:])


def _gdscript_incompatible(payload: dict) -> bool:
    v = payload.get("gdscript_compatible")
    return v is False


class RstExtractor(NodeVisitor):
    def __init__(self, document, *, since: str, source_file: str, prose_only: bool = False):
        super().__init__(document)
        self.since = since
        self.source_file = source_file
        self.prose_only = prose_only
        self.heading_path: list[str] = []
        self.rules: list[MigrationRule] = []
        self.unclassified: list[dict[str, Any]] = []
        self.prose: dict[tuple[str, ...], list[str]] = defaultdict(list)
        self._used_ids: set[str] = set()

    def visit_section(self, node):
        self.heading_path.append(_section_title(node))

    def depart_section(self, node):
        if self.heading_path:
            self.heading_path.pop()

    def visit_table(self, node):
        if not self.prose_only:
            self._handle_table(node)
        raise SkipNode

    def visit_paragraph(self, node):
        text = node.astext().strip()
        if len(text) >= PROSE_MIN_CHARS:
            self.prose[tuple(self.heading_path)].append(text)
        raise SkipNode

    def visit_admonition(self, node):
        text = node.astext().strip()
        if len(text) >= PROSE_MIN_CHARS:
            self.prose[tuple(self.heading_path)].append(text)
        raise SkipNode

    visit_note = visit_admonition
    visit_warning = visit_admonition
    visit_danger = visit_admonition
    visit_attention = visit_admonition
    visit_caution = visit_admonition
    visit_important = visit_admonition
    visit_tip = visit_admonition
    visit_hint = visit_admonition

    def visit_system_message(self, node):
        raise SkipNode

    def visit_comment(self, node):
        raise SkipNode

    def unknown_visit(self, node):
        return

    def unknown_departure(self, node):
        return

    def visit_literal_block(self, node):
        text = node.astext().strip()
        if len(text) >= PROSE_MIN_CHARS:
            self.prose[tuple(self.heading_path)].append(text)
        raise SkipNode

    def _handle_table(self, node):
        tgroups = list(node.children)
        if not tgroups:
            return
        tgroup = tgroups[0]
        headers: list[str] = []
        body_rows: list = []
        for child in tgroup.children:
            if isinstance(child, thead):
                for r in child.children:
                    if isinstance(r, row):
                        headers = [e.astext().strip() for e in _cell_entries(r)]
            elif isinstance(child, tbody):
                body_rows = [r for r in child.children if isinstance(r, row)]

        colmap: dict[str, int] = {}
        for i, h in enumerate(headers):
            key = _header_key(h)
            if key is not None and key not in colmap:
                colmap[key] = i

        is_defaults = "old_default" in colmap and "new_default" in colmap
        heading_l = " ".join(self.heading_path).lower()
        is_behavior_section = "behavior" in heading_l
        section_label = " > ".join(p for p in self.heading_path if p)

        current_owner: str | None = None
        change_idx = colmap.get("change", 0)

        for r in body_rows:
            entries = _cell_entries(r)
            cells: list[tuple[str, list[str]]] = [
                (e.astext().strip(), _literals(e)) for e in entries
            ]
            if _is_owner_row(cells):
                current_owner = cells[0][0].strip() or None
                continue
            if change_idx >= len(cells):
                continue
            change_text, change_lits = cells[change_idx]
            if not change_text:
                continue
            if not change_lits:
                change_lits = re.findall(
                    r"\b[A-Z][A-Za-z0-9]+(?:\.[A-Z][A-Z0-9_]+)+\b", change_text
                )

            payload: dict[str, Any] = {"section": section_label}
            if "gdscript" in colmap and colmap["gdscript"] < len(cells):
                payload["gdscript_compatible"] = _compat_bool(cells[colmap["gdscript"]][0])
            if "csharp_binary" in colmap and colmap["csharp_binary"] < len(cells):
                payload["csharp_binary_compatible"] = _compat_bool(
                    cells[colmap["csharp_binary"]][0]
                )
            if "csharp_source" in colmap and colmap["csharp_source"] < len(cells):
                payload["csharp_source_compatible"] = _compat_bool(
                    cells[colmap["csharp_source"]][0]
                )
            gh_src = change_text
            if "introduced" in colmap and colmap["introduced"] < len(cells):
                gh_src = cells[colmap["introduced"]][0] + " " + gh_src
            gh = GH_RE.search(gh_src)
            if gh:
                payload["github"] = f"GH-{gh.group(1)}"

            kind = _symbol_kind_from_text(change_text)
            classified = True
            extra_tokens: list[str] = []
            moved_to = None
            extra = None

            if is_defaults:
                change = ChangeKind.default
                old_sym = change_lits[-1] if change_lits else None
                new_sym = old_sym
                extra = change_lits[0] if len(change_lits) > 1 else old_sym
                if "old_default" in colmap and colmap["old_default"] < len(cells):
                    payload["old_default"] = cells[colmap["old_default"]][0]
                if "new_default" in colmap and colmap["new_default"] < len(cells):
                    payload["new_default"] = cells[colmap["new_default"]][0]
                semantic_risk = True
                verifier_blind = False
                confidence = None
                agent_action = AgentAction.note_only
            else:
                info = _classify(change_text, change_lits, kind)
                change = info["change"]
                old_sym = info["old"]
                new_sym = info["new"]
                extra = info.get("extra")
                extra_tokens = info.get("extra_tokens") or []
                moved_to = info.get("moved_to")
                classified = info["classified"]
                semantic_risk = change in {ChangeKind.behavior, ChangeKind.default}
                verifier_blind = change == ChangeKind.behavior
                confidence = None if classified else "needs_review"
                if is_behavior_section and classified is False:
                    change = ChangeKind.behavior
                    semantic_risk = True
                    verifier_blind = True
                if moved_to:
                    payload["moved_to"] = moved_to
                # README 6.3: GDScript-incompatible → apply_and_warn, else note_only.
                agent_action = (
                    AgentAction.apply_and_warn
                    if _gdscript_incompatible(payload)
                    else AgentAction.note_only
                )

            tokens = list(dict.fromkeys(change_lits + extra_tokens))
            if old_sym and old_sym not in tokens:
                tokens.insert(0, old_sym)
            if new_sym and new_sym not in tokens:
                tokens.append(new_sym)

            warning = None
            rid = make_id(
                "official_prose",
                self.since,
                current_owner,
                kind.value,
                old_sym or new_sym,
                extra,
            )
            suffix = 2
            base_id = rid
            while rid in self._used_ids:
                rid = f"{base_id}#{suffix}"
                suffix += 1
            self._used_ids.add(rid)
            rule = MigrationRule(
                id=rid,
                old_symbol=old_sym,
                new_symbol=new_sym,
                owner=current_owner,
                symbol_kind=kind,
                change=change,
                match_tokens=tokens,
                since_version=self.since,
                detection_method=DetectionMethod.agent_retrieval,
                semantic_risk=semantic_risk,
                verifier_blind=verifier_blind,
                agent_action=agent_action,
                warning=warning,
                snippet=change_text,
                source="official_prose",
                confidence=confidence,
                payload={k: v for k, v in payload.items() if v is not None},
            )
            self.rules.append(rule)
            if not classified and not is_defaults:
                self.unclassified.append(
                    {
                        "file": self.source_file,
                        "since": self.since,
                        "owner": current_owner,
                        "snippet": change_text,
                        "heading": section_label,
                    }
                )


def _write_prose_jsonl(
    dest: Path,
    buckets: dict[tuple[str, ...], list[str]],
    *,
    since: str,
    source_file: str,
    source: str,
    skip_token_sets: list[list[str]] | None = None,
) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    skip_token_sets = skip_token_sets or []
    with dest.open("w", encoding="utf-8") as fh:
        for heading, parts in buckets.items():
            kept = [p for p in parts if not _overlaps_carveout(p, skip_token_sets)]
            text = "\n\n".join(kept).strip()
            if len(text) < PROSE_MIN_CHARS:
                continue
            rec = {
                "heading_path": list(heading),
                "text": text,
                "since_version": since,
                "source_file": source_file,
                "source": source,
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n


def _overlaps_carveout(text: str, token_sets: list[list[str]]) -> bool:
    lower = text.lower()
    for tokens in token_sets:
        hits = sum(1 for t in tokens if t and t.lower() in lower)
        if hits >= 2:
            return True
    return False


def _load_shader_skip_tokens() -> list[list[str]]:
    path = MANUAL / "shader_3to4_carveout.yaml"
    if not path.exists():
        return [
            ["vertex", "start", "process"],
            ["SCREEN_UV", "NDC"],
            ["light("],
        ]
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = data.get("shader_carveouts") or data.get("entries") or []
    return [e.get("match_tokens") or [] for e in entries]


def _rst_files_for_target(target_version: str) -> list[tuple[Path, str]]:
    target_code = version_to_code(target_version)
    floor = version_to_code("4.0")
    out: list[tuple[Path, str]] = []
    for path in sorted(OFFICIAL.glob("upgrading_to_godot_4.*.rst")):
        m = SINCE_RE.match(path.name)
        if not m:
            continue
        ver = f"4.{m.group(1)}"
        code = version_to_code(ver)
        if floor < code <= target_code:
            out.append((path, ver))
    return out


def extract_file(path: Path, since: str, *, prose_only: bool = False) -> RstExtractor:
    raw = path.read_text(encoding="utf-8")
    doctree = parse_doctree(inject_substitution_defs(raw), str(path))
    visitor = RstExtractor(
        doctree, since=since, source_file=path.name, prose_only=prose_only
    )
    doctree.walkabout(visitor)
    return visitor


def main() -> int:
    manifest = load_manifest()
    target = manifest.get("godot_version") or "4.7.1"
    files = _rst_files_for_target(target)
    if not files:
        print("parse_upgrading_docs: no incremental rst files in range", file=sys.stderr)
        return 1

    all_rules: list[MigrationRule] = []
    all_unclassified: list[dict[str, Any]] = []
    prose_counts: dict[str, int] = {}

    for path, since in files:
        visitor = extract_file(path, since, prose_only=False)
        all_rules.extend(visitor.rules)
        all_unclassified.extend(visitor.unclassified)
        dest = PROSE_DIR / "_raw" / "official_upgrading_guide" / f"{path.name}.prose.jsonl"
        n_prose = _write_prose_jsonl(
            dest,
            visitor.prose,
            since=since,
            source_file=path.name,
            source="official_prose",
        )
        prose_counts[dest.name] = n_prose
        print(
            f"  {path.name}: rules={len(visitor.rules)} "
            f"unclassified={len(visitor.unclassified)} prose_blocks={n_prose}"
        )

    # 3→4 total guide: copy whole file; prose only from Updating shaders.
    guide = OFFICIAL / "upgrading_to_godot_4.rst"
    ctx_dir = ARTIFACTS / "agent_context"
    ctx_dir.mkdir(parents=True, exist_ok=True)
    (ctx_dir / "upgrading_to_godot_4.rst").write_text(
        guide.read_text(encoding="utf-8"), encoding="utf-8"
    )

    shader_visitor = extract_file(guide, "4.0", prose_only=True)
    shader_buckets = {
        k: v for k, v in shader_visitor.prose.items() if "Updating shaders" in k
    }
    skip_tokens = _load_shader_skip_tokens()
    shader_dest = PROSE_DIR / "_raw" / "official_upgrading_guide" / "upgrading_to_godot_4.rst.updating_shaders.prose.jsonl"
    n_shader = _write_prose_jsonl(
        shader_dest,
        shader_buckets,
        since="4.0",
        source_file=guide.name,
        source="official_prose_3to4_shader",
        skip_token_sets=skip_tokens,
    )
    prose_counts[shader_dest.name] = n_shader
    print(f"  {guide.name} Updating shaders: prose_blocks={n_shader} (no A-layer rows)")

    out = INTERMEDIATE / "rst_4x.jsonl"
    n = write_jsonl(out, all_rules)
    report = {
        "files": [p.name for p, _ in files],
        "rule_count": n,
        "unclassified_count": len(all_unclassified),
        "unclassified": all_unclassified,
        "prose_counts": prose_counts,
        "target_version": target,
    }
    write_report_json("rst", report)
    print(f"parse_upgrading_docs: wrote {n} rows → {out}")
    print(f"  unclassified rows kept as behavior/needs_review: {len(all_unclassified)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
