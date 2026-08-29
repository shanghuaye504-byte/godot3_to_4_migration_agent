"""Type D processor: official Godot blog HTML -> Document IR.

Input:  after_preprocess/official_blog/*.blocks.jsonl
Output: ir/official_blog/*.ir.json

Workflow: rag/vault/tier_b_prose/CHUNKING.md §6.5
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
    topic_map_select,
)

BUCKET = "official_blog"
INPUT_DIR = (
    Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose" / "after_preprocess" / BUCKET
)
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose" / "ir" / BUCKET
POLICY_DIR = Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose" / "policy"

_BACKTICK_RE = re.compile(r"`([^`]+)`")
_SOURCE_URLS = {
    "core-refactoring-progress-report-2.html": (
        "https://godotengine.org/article/core-refactoring-progress-report-2/"
    ),
    "multiplayer-changes-godot-4-0-report-2.html": (
        "https://godotengine.org/article/multiplayer-changes-godot-4-0-report-2/"
    ),
}


def _review_mode() -> bool:
    return os.environ.get("TIER_B_REVIEW_MODE", "").strip().lower() in {"1", "true", "yes"}


def _load_yaml_list(name: str, key: str) -> list[str]:
    """Load a list from a YAML policy file; missing/empty files return []."""
    path = POLICY_DIR / name
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [str(x) for x in (data.get(key) or [])]


def _load_topic_map() -> dict:
    """Load topic_map.yaml; missing/empty files return {}."""
    path = POLICY_DIR / "topic_map.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def process_file(blocks_path: Path) -> ProseDocument | None:
    """Filter + select blocks and build ProseDocument (does not write).

    Type D (official blog) uses a heading denylist for noise and a topic map
    to identify migration-relevant sections. When the topic map is empty or
    missing, every block is kept so no policy gap silently drops content.
    """
    original = read_blocks_jsonl(blocks_path)
    source_file = blocks_path.name.removesuffix(".blocks.jsonl")
    patterns = load_boilerplate_patterns(POLICY_DIR / "boilerplate_patterns.txt")
    topic_map = _load_topic_map()
    denylist = _load_yaml_list("heading_denylist.yaml", "denylist")

    blocks = length_filter(original, 80)
    blocks = boilerplate_filter(blocks, patterns)
    blocks = noise_filter(blocks)
    topic = topic_map_select(blocks, topic_map)
    deny = heading_denylist_select(blocks, denylist)
    keep, drop, uncertain = combine_select(deny, topic)

    # Motivation paragraphs in the same subsection as a topic hit stay together.
    keep_paths = {tuple(b.heading_path) for b in keep}
    extra: list[ProseBlock] = []
    keep_ids = {b.block_id for b in keep}
    drop_ids = {b.block_id for b in drop}
    for block in uncertain:
        if block.block_id in keep_ids or block.block_id in drop_ids:
            continue
        if tuple(block.heading_path) in keep_paths and block.type != "heading":
            extra.append(block)
    keep = keep + extra

    if _review_mode():
        print(f"# review {source_file} keep={len(keep)} drop={len(drop)}")
        for block in keep:
            snippet = re.sub(r"\s+", " ", block.text)[:160]
            print(f"[keep] {block.block_id} {' > '.join(block.heading_path)}: {snippet}")
        return None

    title = next((b.text for b in original if b.type == "heading"), source_file)
    tokens: list[str] = []
    blob = "\n".join(b.text for b in keep)
    for match in _BACKTICK_RE.findall(blob):
        tok = match.strip()
        if tok and tok not in tokens:
            tokens.append(tok)
    for topic_name in topic_map.get("topics") or []:
        if str(topic_name).lower() in blob.lower() and topic_name not in tokens:
            tokens.append(str(topic_name))
    return ProseDocument(
        schema_version=1,
        doc_id=make_doc_id("html_blog", source_file),
        source="official_blog",
        source_file=source_file,
        source_url=_SOURCE_URLS.get(source_file),
        source_type="html_blog",
        since_version="4.0",
        confidence="verified",
        title=title,
        keep=True,
        match_tokens=tokens[:48],
        blocks=keep,
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
    print(f"official_blog: {written} IR files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
