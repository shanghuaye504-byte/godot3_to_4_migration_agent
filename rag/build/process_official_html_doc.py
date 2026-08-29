"""Type C processor: official Sphinx HTML -> Document IR.

Input:  after_preprocess/official_html_doc/*.blocks.jsonl
Output: ir/official_html_doc/*.ir.json

Workflow: rag/vault/tier_b_prose/CHUNKING.md §6.4
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_BUILD_DIR = Path(__file__).resolve().parent
if str(_BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(_BUILD_DIR))

from prose_preprocessing_util.filters import (  # noqa: E402
    boilerplate_filter,
    length_filter,
    load_boilerplate_patterns,
    noise_filter,
    signature_density_filter,
)
from prose_preprocessing_util.ir import (  # noqa: E402
    ProseBlock,
    ProseDocument,
    make_doc_id,
    read_blocks_jsonl,
    write_ir,
)

BUCKET = "official_html_doc"
INPUT_DIR = (
    Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose" / "after_preprocess" / BUCKET
)
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose" / "ir" / BUCKET
POLICY_DIR = Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose" / "policy"

_BACKTICK_RE = re.compile(r"`([^`]+)`")
_SOURCE_URLS = {
    "using_character_body_2d.html": (
        "https://docs.godotengine.org/en/stable/tutorials/physics/"
        "using_character_body_2d.html"
    ),
    "class_fileaccess.html": (
        "https://docs.godotengine.org/en/stable/classes/class_fileaccess.html"
    ),
    "class_editorplugin.html": (
        "https://docs.godotengine.org/en/4.4/classes/class_editorplugin.html"
    ),
}


def _review_mode() -> bool:
    return os.environ.get("TIER_B_REVIEW_MODE", "").strip().lower() in {"1", "true", "yes"}


def _deduplicate_blocks(blocks: list[ProseBlock]) -> list[ProseBlock]:
    """Drop later blocks whose text exactly duplicates an earlier block."""
    seen: set[str] = set()
    kept: list[ProseBlock] = []
    for block in blocks:
        key = block.text.strip()
        if key in seen:
            continue
        seen.add(key)
        kept.append(block)
    return kept


def process_file(blocks_path: Path) -> ProseDocument | None:
    """Filter blocks and build ProseDocument (does not write)."""
    original = read_blocks_jsonl(blocks_path)
    source_file = blocks_path.name.removesuffix(".blocks.jsonl")
    patterns = load_boilerplate_patterns(POLICY_DIR / "boilerplate_patterns.txt")
    blocks = length_filter(original, 80)
    blocks = boilerplate_filter(blocks, patterns)
    blocks = noise_filter(blocks)
    blocks = signature_density_filter(blocks, 0.5)
    blocks = _deduplicate_blocks(blocks)
    if _review_mode():
        kept_ids = {b.block_id for b in blocks}
        dropped = [b for b in original if b.block_id not in kept_ids]
        print(f"# review {source_file} dropped={len(dropped)} kept={len(blocks)}")
        for block in dropped[:40]:
            snippet = re.sub(r"\s+", " ", block.text)[:120]
            print(f"[drop] {block.block_id} {block.type}: {snippet}")
        return None

    title = next((b.text for b in original if b.type == "heading"), source_file)
    tokens = []
    blob = "\n".join(b.text for b in blocks)
    for match in _BACKTICK_RE.findall(blob):
        tok = match.strip()
        if tok and tok not in tokens:
            tokens.append(tok)
    return ProseDocument(
        schema_version=1,
        doc_id=make_doc_id("html_sphinx", source_file),
        source="official_doc",
        source_file=source_file,
        source_url=_SOURCE_URLS.get(source_file),
        source_type="html_sphinx",
        since_version="4.0",
        confidence="verified",
        title=title,
        keep=True,
        match_tokens=tokens[:48],
        blocks=blocks,
    )


def main() -> int:
    """Process all files in INPUT_DIR and write IR to OUTPUT_DIR."""
    if not INPUT_DIR.is_dir():
        print(f"input dir not found: {INPUT_DIR}", file=sys.stderr)
        print("Run scan_tier_b_raw.py first.", file=sys.stderr)
        return 1
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for path in sorted(INPUT_DIR.glob("*.blocks.jsonl")):
        doc = process_file(path)
        if doc is None:
            continue
        dest = OUTPUT_DIR / f"{doc.source_file}.ir.json"
        write_ir(doc, dest)
        print(f"  wrote {dest.name} ({len(doc.blocks)} blocks)")
        written += 1
    print(f"official_html_doc: {written} IR files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
