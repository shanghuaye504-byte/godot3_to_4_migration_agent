"""Human-in-the-loop review queue I/O.

Specification: rag/vault/tier_b_prose/CHUNKING.md §4.6 and §6.7
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class ReviewItem(BaseModel):
    """A candidate block proposed for human review."""

    doc_id: str
    block_id: str
    text: str
    proposed: str  # keep | drop
    channel: str  # heuristic | llm | manual
    reason: str


def append_queue(path: Path, items: list[ReviewItem]) -> None:
    """Append review items to a JSONL queue, creating the file if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for item in items:
            fh.write(item.model_dump_json() + "\n")


def read_queue(path: Path) -> list[ReviewItem]:
    """Read all review items from a queue JSONL. Missing file → empty list."""
    if not path.exists():
        return []
    items: list[ReviewItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(ReviewItem.model_validate_json(line))
    return items
