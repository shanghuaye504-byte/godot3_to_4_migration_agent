"""Shared prose preprocessing utilities.

See rag/vault/tier_b_prose/CHUNKING.md for the full workflow.
"""

from __future__ import annotations

from .filters import (
    boilerplate_filter,
    github_noise_filter,
    length_filter,
    load_boilerplate_patterns,
    signature_density_filter,
)
from .heading_path import HeadingPath
from .ir import (
    ProseBlock,
    ProseDocument,
    assign_block_ids,
    make_doc_id,
    read_blocks_jsonl,
    read_ir,
    write_blocks_jsonl,
    write_ir,
)
from .parsers import parse_html, parse_markdown, parse_rst
from .review_queue import ReviewItem, append_queue, read_queue
from .selectors import (
    combine_select,
    heading_allowlist_select,
    heading_denylist_select,
    keyword_allowlist_select,
    maintainer_select,
    topic_map_select,
)

__all__ = [
    "HeadingPath",
    "ProseBlock",
    "ProseDocument",
    "ReviewItem",
    "append_queue",
    "assign_block_ids",
    "boilerplate_filter",
    "combine_select",
    "github_noise_filter",
    "heading_allowlist_select",
    "heading_denylist_select",
    "keyword_allowlist_select",
    "length_filter",
    "load_boilerplate_patterns",
    "maintainer_select",
    "make_doc_id",
    "parse_html",
    "parse_markdown",
    "parse_rst",
    "read_blocks_jsonl",
    "read_ir",
    "read_queue",
    "signature_density_filter",
    "topic_map_select",
    "write_blocks_jsonl",
    "write_ir",
]
