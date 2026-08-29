"""Type E processor: GitHub PR / Issue / Discussion -> review queue.

Input:  after_preprocess/github_{pr,issue,discussion}/*.blocks.jsonl
Output: review_queue.jsonl (NO direct IR)

_raw/github_* holds API Markdown (download_github_api.py). scan_tier_b_raw.py
parses those .md files into jsonl; this script only filters that jsonl.
It does not call the GitHub API.

This is a human-in-the-loop entry point: every surviving block is written to
the shared review queue so a maintainer can decide which ones to keep. After
review, selected excerpts are written to curation/*.yaml and compiled into IR
by compile_curation.py.

Workflow: rag/vault/tier_b_prose/CHUNKING.md §6.6 (updated)
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
    github_noise_filter,
    length_filter,
    noise_filter,
)
from prose_preprocessing_util.ir import read_blocks_jsonl  # noqa: E402
from prose_preprocessing_util.review_queue import (  # noqa: E402
    ReviewItem,
    append_queue,
)

BUCKETS = ["github_pr", "github_issue", "github_discussion"]
BASE_DIR = Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose"
QUEUE_PATH = (
    Path(__file__).resolve().parent.parent / "build" / "intermediate" / "prose_review_queue.jsonl"
)

_SOURCE_URLS = {
    "godot_pull_41794.md": "https://github.com/godotengine/godot/pull/41794",
    "godot_pull_65271.md": "https://github.com/godotengine/godot/pull/65271",
    "godot-docs_issue_5577.md": "https://github.com/godotengine/godot-docs/issues/5577",
    "godot-docs_issue_6265.md": "https://github.com/godotengine/godot-docs/issues/6265",
    "godot-proposals_discussion_6192.md": (
        "https://github.com/godotengine/godot-proposals/discussions/6192"
    ),
}

_SOURCE_TYPE = {
    "github_pr": "github_pr",
    "github_issue": "github_issue",
    "github_discussion": "github_discussion",
}


def _review_mode() -> bool:
    return os.environ.get("TIER_B_REVIEW_MODE", "").strip().lower() in {"1", "true", "yes"}


def _is_opening_post(block, op_title: str | None) -> bool:
    """Return True if the block belongs to the opening post of the thread."""
    if op_title is None:
        return False
    return op_title in block.heading_path or (block.type == "heading" and block.text == op_title)


def process_file(blocks_path: Path, bucket: str) -> list[ReviewItem]:
    """Filter blocks and produce ReviewItem candidates for the queue."""
    source_file = blocks_path.name.removesuffix(".blocks.jsonl")
    blocks = read_blocks_jsonl(blocks_path)
    blocks = noise_filter(blocks)
    blocks = github_noise_filter(blocks)
    blocks = length_filter(blocks, 20)

    op_title = next((b.text for b in blocks if b.type == "heading"), None)

    items: list[ReviewItem] = []
    for block in blocks:
        reason_bits: list[str] = []
        if block.type == "code" or "```" in block.text:
            reason_bits.append("code_block")
        if _is_opening_post(block, op_title):
            reason_bits.append("opening_post")
        if block.subtype:
            reason_bits.append(f"author:{block.subtype}")

        snippet = block.text.strip()
        if len(snippet) > 500:
            snippet = snippet[:497] + "..."

        items.append(
            ReviewItem(
                doc_id=f"{bucket}/{source_file}",
                block_id=block.block_id,
                text=snippet,
                proposed="keep",
                channel="heuristic",
                reason="; ".join(reason_bits) or "survived_noise_filter",
            )
        )
    return items


def main() -> int:
    """Process all three github buckets and append candidates to the review queue."""
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    for bucket in BUCKETS:
        input_dir = BASE_DIR / "after_preprocess" / bucket
        if not input_dir.is_dir():
            print(f"  skip {bucket}: no after_preprocess dir")
            continue
        for path in sorted(input_dir.glob("*.blocks.jsonl")):
            items = process_file(path, bucket)
            if _review_mode():
                print(f"# review {bucket}/{path.name} candidates={len(items)}")
                for item in items:
                    snippet = re.sub(r"\s+", " ", item.text)[:160]
                    print(f"[candidate] {item.block_id}: {snippet}")
                continue
            if items:
                append_queue(QUEUE_PATH, items)
                total += len(items)
                print(f"  {bucket}/{path.name}: {len(items)} candidates")

    if _review_mode():
        return 0

    print()
    print(
        "请查看 review_queue.jsonl，挑选需要入库的段落并写入 "
        "vault/tier_b_prose/curation/<stem>.yaml，然后运行 compile_curation.py"
    )
    print(f"queue: {QUEUE_PATH} ({total} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
