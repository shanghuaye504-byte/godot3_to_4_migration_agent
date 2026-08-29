"""Type B processor: official GDScript rst -> Document IR.

Input:  after_preprocess/official_gdscript_doc/*.blocks.jsonl
Output: ir/official_gdscript_doc/*.ir.json

Workflow: rag/vault/tier_b_prose/CHUNKING.md §6.3
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_BUILD_DIR = Path(__file__).resolve().parent
if str(_BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(_BUILD_DIR))

import yaml  # noqa: E402

from prose_preprocessing_util.filters import (  # noqa: E402
    boilerplate_filter,
    length_filter,
    load_boilerplate_patterns,
    noise_filter,
)
from prose_preprocessing_util.ir import (  # noqa: E402
    ProseBlock,
    ProseDocument,
    make_doc_id,
    read_blocks_jsonl,
    write_ir,
)
from prose_preprocessing_util.selectors import (  # noqa: E402
    combine_select,
    heading_denylist_select,
    keyword_allowlist_select,
)

BUCKET = "official_gdscript_doc"
INPUT_DIR = (
    Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose" / "after_preprocess" / BUCKET
)
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose" / "ir" / BUCKET
POLICY_DIR = Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose" / "policy"

_BACKTICK_RE = re.compile(r"`([^`]+)`")
_SOURCE_URLS = {
    "gdscript_basics.rst": (
        "https://github.com/godotengine/godot-docs/blob/master/"
        "tutorials/scripting/gdscript/gdscript_basics.rst"
    ),
    "gdscript_styleguide.rst": (
        "https://github.com/godotengine/godot-docs/blob/master/"
        "tutorials/scripting/gdscript/gdscript_styleguide.rst"
    ),
    "signals_step_by_step.rst": (
        "https://github.com/godotengine/godot-docs/blob/master/"
        "getting_started/step_by_step/signals.rst"
    ),
}


def _review_mode() -> bool:
    return os.environ.get("TIER_B_REVIEW_MODE", "").strip().lower() in {"1", "true", "yes"}


def load_policies() -> dict:
    """Load heading_denylist.yaml, keyword_allowlist.yaml, boilerplate_patterns.txt.

    Missing or empty policy files are treated as "pass through": no filtering
    is applied for that slot. This keeps the pipeline robust and conservative.
    """

    def _list(name: str, key: str) -> list[str]:
        path = POLICY_DIR / name
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return [str(x) for x in (data.get(key) or [])]

    return {
        "denylist": _list("heading_denylist.yaml", "denylist"),
        "keywords": _list("keyword_allowlist.yaml", "keywords"),
        "boilerplate": load_boilerplate_patterns(POLICY_DIR / "boilerplate_patterns.txt"),
    }


def process_file(blocks_path: Path) -> ProseDocument | None:
    """Filter + select blocks and build ProseDocument (does not write).

    Strategy for type B (official GDScript docs):
      - Denylist drops only clearly irrelevant headings.
      - Keyword allowlist is used only to populate ``match_tokens`` and to
        highlight migration-relevant blocks; it never drops a block.
      - Everything else is kept, because official docs are high-signal and we
        want to avoid losing migration knowledge.
    """
    policies = load_policies()
    original = read_blocks_jsonl(blocks_path)
    source_file = blocks_path.name.removesuffix(".blocks.jsonl")
    blocks = length_filter(original, 40)
    blocks = boilerplate_filter(blocks, policies["boilerplate"])
    blocks = noise_filter(blocks)
    den = heading_denylist_select(blocks, policies["denylist"])
    kw = keyword_allowlist_select(blocks, policies["keywords"])
    keep, drop, uncertain = combine_select(den, kw)
    # Keep everything that was not explicitly dropped by the denylist.
    kept = keep + uncertain
    if _review_mode():
        _print_review(source_file, drop, kept)
        return None

    title = _first_heading(original)
    tokens = _match_tokens(kept, policies["keywords"])
    return ProseDocument(
        schema_version=1,
        doc_id=make_doc_id("rst", source_file),
        source="official_doc",
        source_file=source_file,
        source_url=_SOURCE_URLS.get(source_file),
        source_type="rst",
        since_version="4.0",
        confidence="verified",
        title=title,
        keep=True,
        match_tokens=tokens,
        blocks=kept,
    )


def _first_heading(blocks: list[ProseBlock]) -> str | None:
    for block in blocks:
        if block.type == "heading" and block.text.strip():
            return block.text.strip()
    return None


def _match_tokens(blocks: list[ProseBlock], keywords: list[str]) -> list[str]:
    blob = "\n".join(b.text for b in blocks)
    found: list[str] = []
    for match in _BACKTICK_RE.findall(blob):
        tok = match.strip()
        if tok and tok not in found:
            found.append(tok)
    lower = blob.lower()
    for kw in keywords:
        if kw.lower() in lower and kw not in found:
            found.append(kw)
    return found[:48]


def _print_review(
    source_file: str, drop: list[ProseBlock], kept: list[ProseBlock]
) -> None:
    print(f"# review {source_file}")
    print(f"# drop={len(drop)} kept={len(kept)}")
    for label, group in (("drop", drop), ("kept", kept)):
        for block in group:
            snippet = re.sub(r"\s+", " ", block.text)[:160]
            print(f"[{label}] {block.block_id} {block.type}: {snippet}")


def main() -> int:
    """Process all files in INPUT_DIR and write IR to OUTPUT_DIR."""
    if not INPUT_DIR.is_dir():
        print(f"input dir not found: {INPUT_DIR}", file=sys.stderr)
        print("Run scan_tier_b_raw.py first.", file=sys.stderr)
        return 1
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = sorted(INPUT_DIR.glob("*.blocks.jsonl"))
    if not paths:
        print(f"no blocks.jsonl in {INPUT_DIR}", file=sys.stderr)
        return 1
    written = 0
    for path in paths:
        doc = process_file(path)
        if doc is None:
            continue
        dest = OUTPUT_DIR / f"{doc.source_file}.ir.json"
        write_ir(doc, dest)
        print(f"  wrote {dest.name} ({len(doc.blocks)} blocks)")
        written += 1
    print(f"official_gdscript_doc: {written} IR files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
