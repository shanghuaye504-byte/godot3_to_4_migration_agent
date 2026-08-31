"""Stage 1: scan _raw/ buckets and normalize every file into typed blocks.

This script does NOT apply policy filters or write IR. It only parses formats
and writes block drafts to after_preprocess/<bucket>/<file>.blocks.jsonl.

Workflow: rag/vault/tier_b_prose/CHUNKING.md §5
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add workspace root so we can import prose_preprocessing_util.
_BUILD_DIR = Path(__file__).resolve().parent
if str(_BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(_BUILD_DIR))

from prose_preprocessing_util.ir import assign_block_ids, write_blocks_jsonl  # noqa: E402
from prose_preprocessing_util.parsers import (  # noqa: E402
    parse_html,
    parse_markdown,
    parse_rst,
)

RAW_DIR = Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose" / "_raw"
PREPROCESS_DIR = (
    Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose" / "after_preprocess"
)

# Type A lives under official_upgrading_guide as *.prose.jsonl and is lifted
# by chunk_prose.py; the scanner does not touch it.
SCAN_BUCKETS = [
    "official_gdscript_doc",
    "official_html_doc",
    "official_blog",
    "github_pr",
    "github_issue",
    "github_discussion",
    "community_blog",
    "community_gist",
]

_SKIP_NAMES = {"download_summary.json", ".gitkeep"}
_SKIP_SUFFIXES = {".prose.jsonl"}


def html_profile_for_bucket(bucket: str) -> str:
    """Map bucket name to html parser profile (CHUNKING.md §5.2)."""
    if bucket == "official_html_doc":
        return "sphinx"
    if bucket == "official_blog":
        return "godot_blog"
    if bucket in {"community_blog", "community_gist"}:
        return "community"
    raise ValueError(f"no HTML profile for bucket {bucket!r}")


def scan_bucket(bucket: str) -> int:
    """Parse every source file in ``_raw/<bucket>/`` and write blocks.jsonl."""
    src_dir = RAW_DIR / bucket
    if not src_dir.is_dir():
        print(f"  skip {bucket}: missing {src_dir}")
        return 0
    out_dir = PREPROCESS_DIR / bucket
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in sorted(src_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name in _SKIP_NAMES:
            continue
        if any(path.name.endswith(suf) for suf in _SKIP_SUFFIXES):
            continue
        blocks = _parse_file(path, bucket)
        blocks = assign_block_ids(blocks)
        dest = out_dir / f"{path.name}.blocks.jsonl"
        write_blocks_jsonl(blocks, dest)
        print(f"  {bucket}/{path.name}: {len(blocks)} blocks -> {dest.name}")
        count += 1
    return count


def _parse_file(path: Path, bucket: str):
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".rst":
        return parse_rst(text, str(path))
    if suffix in {".html", ".htm"}:
        return parse_html(text, html_profile_for_bucket(bucket))
    if suffix in {".md", ".markdown"} or suffix == "":
        return parse_markdown(text)
    print(f"  skip unrecognized extension: {path.name}", file=sys.stderr)
    return []


def main() -> int:
    """Iterate over the source buckets and call scan_bucket()."""
    if not RAW_DIR.is_dir():
        print(f"raw dir not found: {RAW_DIR}", file=sys.stderr)
        return 1
    total = 0
    for bucket in SCAN_BUCKETS:
        print(f"==> {bucket}")
        total += scan_bucket(bucket)
    print(f"scanned {total} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
