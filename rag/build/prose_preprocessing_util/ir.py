"""Document IR schema and I/O helpers.

Specification: rag/vault/tier_b_prose/CHUNKING.md §3
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

BLOCK_TYPES = (
    "heading",
    "paragraph",
    "code",
    "list",
    "admonition",
    "quote",
)


class ProseBlock(BaseModel):
    """A single semantic block inside a prose document."""

    block_id: str
    type: str  # heading | paragraph | code | list | admonition | quote
    text: str
    heading_path: list[str]
    level: int | None = None
    language: str | None = None
    subtype: str | None = None


class ProseDocument(BaseModel):
    """Document IR: the unified intermediate representation for all prose sources."""

    schema_version: int = 1
    doc_id: str
    source: str
    source_file: str
    source_url: str | None = None
    source_type: str
    since_version: str | None = None
    confidence: str | None = None
    title: str | None = None
    keep: bool = True
    match_tokens: list[str] = Field(default_factory=list)
    blocks: list[ProseBlock] = Field(default_factory=list)


def make_doc_id(source_type: str, source_file: str) -> str:
    """Return a stable doc_id like ``<source_type>/<source_file>``."""
    return f"{source_type}/{source_file}"


def assign_block_ids(blocks: list[ProseBlock]) -> list[ProseBlock]:
    """Renumber blocks as ``b0001``, ``b0002``, ... keeping other fields."""
    out: list[ProseBlock] = []
    for i, block in enumerate(blocks, start=1):
        out.append(block.model_copy(update={"block_id": f"b{i:04d}"}))
    return out


def read_ir(path: Path) -> ProseDocument:
    """Read an ``.ir.json`` file and return a validated ``ProseDocument``."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return ProseDocument.model_validate(data)


def write_ir(doc: ProseDocument, path: Path) -> None:
    """Write ``ProseDocument`` to an ``.ir.json`` file (UTF-8, pretty)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = doc.model_dump(mode="json")
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_blocks_jsonl(path: Path) -> list[ProseBlock]:
    """Read a ``.blocks.jsonl`` draft produced by the scanner."""
    blocks: list[ProseBlock] = []
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        blocks.append(ProseBlock.model_validate(json.loads(line)))
    return blocks


def write_blocks_jsonl(blocks: list[ProseBlock], path: Path) -> None:
    """Write block drafts, one JSON object per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for block in blocks:
            fh.write(block.model_dump_json() + "\n")
