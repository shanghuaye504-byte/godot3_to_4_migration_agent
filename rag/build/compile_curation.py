"""Compile human-curated YAML excerpts into Document IR.

Input:  rag/vault/tier_b_prose/curation/*.yaml
Output: rag/vault/tier_b_prose/ir/community_blog/*.ir.json
        rag/vault/tier_b_prose/ir/community_gist/*.ir.json

Workflow: rag/vault/tier_b_prose/CHUNKING.md §7
"""

from __future__ import annotations

import sys
from pathlib import Path

_BUILD_DIR = Path(__file__).resolve().parent
if str(_BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(_BUILD_DIR))

import yaml  # noqa: E402

from prose_preprocessing_util.ir import (  # noqa: E402
    ProseBlock,
    ProseDocument,
    assign_block_ids,
    make_doc_id,
    write_ir,
)

CURATION_DIR = Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose" / "curation"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose" / "ir"

_SOURCE_TYPE_TO_BUCKET = {
    "community_blog": "community_blog",
    "gist": "community_gist",
}


def load_curation(path: Path) -> dict:
    """Load a curation YAML file (CHUNKING.md §7.1)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"curation file is not a mapping: {path}")
    return data


def build_ir(data: dict) -> ProseDocument:
    """Convert curation YAML into ProseDocument."""
    source_file = str(data["source_file"])
    source_type = str(data.get("source_type") or "community_blog")
    blocks: list[ProseBlock] = []
    for excerpt in data.get("excerpts") or []:
        heading_path = [str(p) for p in (excerpt.get("heading_path") or [])]
        text = (excerpt.get("text") or "").strip()
        if text:
            blocks.append(
                ProseBlock(
                    block_id="b0000",
                    type="paragraph",
                    text=text,
                    heading_path=heading_path,
                )
            )
        code = (excerpt.get("code") or "").strip()
        if code:
            blocks.append(
                ProseBlock(
                    block_id="b0000",
                    type="code",
                    text=code,
                    heading_path=heading_path,
                    language=excerpt.get("language"),
                )
            )
    blocks = assign_block_ids(blocks)
    tokens = [str(t) for t in (data.get("match_tokens") or [])]
    return ProseDocument(
        schema_version=1,
        doc_id=make_doc_id(source_type, source_file),
        source=str(data.get("source") or "community_prose"),
        source_file=source_file,
        source_url=data.get("source_url"),
        source_type=source_type,
        since_version=str(data.get("since_version") or "4.0"),
        confidence=str(data.get("confidence") or "needs_review"),
        title=data.get("title"),
        keep=True,
        match_tokens=tokens,
        blocks=blocks,
    )


def _output_path(stem: str, data: dict) -> Path:
    source_type = str(data.get("source_type") or "community_blog")
    bucket = _SOURCE_TYPE_TO_BUCKET.get(source_type, "community_blog")
    return OUTPUT_DIR / bucket / f"{stem}.ir.json"


def main() -> int:
    """Compile all curation/*.yaml files into ir/community_*/*.ir.json."""
    if not CURATION_DIR.is_dir():
        print(f"curation dir not found (nothing to compile): {CURATION_DIR}")
        return 0
    paths = sorted(p for p in CURATION_DIR.glob("*.yaml") if p.name != ".gitkeep")
    paths += sorted(CURATION_DIR.glob("*.yml"))
    if not paths:
        print("no curation YAML files; write vault/tier_b_prose/curation/<stem>.yaml first")
        return 0
    written = 0
    for path in paths:
        data = load_curation(path)
        doc = build_ir(data)
        dest = _output_path(path.stem, data)
        write_ir(doc, dest)
        print(f"  wrote {dest.relative_to(OUTPUT_DIR.parent)} ({len(doc.blocks)} blocks)")
        written += 1
    print(f"compile_curation: {written} IR files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
