"""Type F/G processor: community blog / gist -> review queue.

Input:  after_preprocess/community_blog/*.blocks.jsonl
        after_preprocess/community_gist/*.blocks.jsonl
Output: review_queue.jsonl (NO direct IR)

This is the human-in-the-loop entry point. After running this script, the
maintainer must review review_queue.jsonl and write selected excerpts to
curation/<stem>.yaml. Then compile_curation.py produces the final IR.

Heuristic keyword policy lives in policy/community_keywords.yaml. When the
policy is empty or missing, every non-heading block that survives noise
filtering becomes a candidate so nothing is silently dropped.

Workflow: rag/vault/tier_b_prose/CHUNKING.md §6.7 and §6.8
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
from prose_preprocessing_util.ir import ProseBlock, read_blocks_jsonl  # noqa: E402
from prose_preprocessing_util.review_queue import (  # noqa: E402
    ReviewItem,
    append_queue,
)

BUCKETS = ["community_blog", "community_gist"]
BASE_DIR = Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose"
PREPROCESS_DIR = BASE_DIR / "after_preprocess"
POLICY_DIR = BASE_DIR / "policy"
QUEUE_PATH = (
    Path(__file__).resolve().parent.parent / "build" / "intermediate" / "prose_review_queue.jsonl"
)


def _review_mode() -> bool:
    return os.environ.get("TIER_B_REVIEW_MODE", "").strip().lower() in {"1", "true", "yes"}


def load_community_keywords() -> list[str]:
    """Load community keyword policy; missing/empty files return []."""
    path = POLICY_DIR / "community_keywords.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [str(x) for x in (data.get("keywords") or [])]


def heuristic_candidates(blocks: list[ProseBlock], keywords: list[str]) -> list[ProseBlock]:
    """Select candidate blocks containing API names, code, or migration keywords.

    If ``keywords`` is empty, every non-heading block that passed earlier
    filters is treated as a candidate. This prevents a policy gap from
    silently dropping potentially useful community content.
    """
    out: list[ProseBlock] = []
    for block in blocks:
        if block.type == "heading":
            continue
        if block.type == "code":
            out.append(block)
            continue
        if not keywords:
            out.append(block)
            continue
        lower = block.text.lower()
        if "`" in block.text or any(kw in lower for kw in keywords):
            out.append(block)
    return out


def process_bucket(bucket: str, keywords: list[str]) -> int:
    """Generate review candidates for one community bucket. Does not write IR."""
    input_dir = PREPROCESS_DIR / bucket
    if not input_dir.is_dir():
        print(f"  skip {bucket}: no after_preprocess dir")
        return 0
    patterns = load_boilerplate_patterns(POLICY_DIR / "boilerplate_patterns.txt")
    source_type = "community_blog" if bucket == "community_blog" else "gist"
    n_items = 0
    for path in sorted(input_dir.glob("*.blocks.jsonl")):
        source_file = path.name.removesuffix(".blocks.jsonl")
        blocks = read_blocks_jsonl(path)
        blocks = length_filter(blocks, 80)
        blocks = boilerplate_filter(blocks, patterns)
        blocks = noise_filter(blocks)
        candidates = heuristic_candidates(blocks, keywords)
        items: list[ReviewItem] = []
        for block in candidates:
            snippet = block.text.strip()
            if len(snippet) > 500:
                snippet = snippet[:497] + "..."
            reason_bits = []
            if block.type == "code":
                reason_bits.append("code_block")
            if "`" in block.text:
                reason_bits.append("backtick_api")
            hits = [kw for kw in keywords if kw in block.text.lower()]
            if hits:
                reason_bits.append("community_keywords: " + "+".join(hits[:4]))
            items.append(
                ReviewItem(
                    doc_id=f"{source_type}/{source_file}",
                    block_id=block.block_id,
                    text=snippet,
                    proposed="keep",
                    channel="heuristic",
                    reason="; ".join(reason_bits) or "heuristic",
                )
            )

        if _review_mode():
            print(f"# review {bucket}/{source_file} candidates={len(items)}")
            for item in items:
                s = re.sub(r"\s+", " ", item.text)[:160]
                print(f"[candidate] {item.block_id}: {s}")
            continue

        if items:
            append_queue(QUEUE_PATH, items)
            n_items += len(items)
            print(f"  {bucket}/{source_file}: {len(items)} candidates")
    return n_items


def main() -> int:
    """Process community_blog and community_gist, then print reviewer instructions."""
    if _review_mode():
        print("# review mode: community buckets")
    else:
        QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)

    keywords = load_community_keywords()
    total = 0
    for bucket in BUCKETS:
        print(f"==> {bucket}")
        total += process_bucket(bucket, keywords)

    if _review_mode():
        return 0

    print()
    print(
        "请查看 review_queue.jsonl，挑选需要入库的段落并写入 curation/.yaml，"
        "然后运行 compile_curation.py"
    )
    print(f"queue: {QUEUE_PATH} ({total} items)")
    print("next: write vault/tier_b_prose/curation/<stem>.yaml")
    print("then: uv run python rag/build/compile_curation.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
