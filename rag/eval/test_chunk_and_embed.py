"""Tests for the single chunker in ``chunk_and_embed.py``.

Embedding (downloading ``bge-small-en-v1.5``) is **not** part of the default
unit suite: it needs network + a few hundred MB on first run. The chunker
itself is a pure function of IR → ``ProseChunk``, which is what we lock here.

Run embedding separately with::

    uv run python build/chunk_and_embed.py
"""

from __future__ import annotations

import json
from pathlib import Path

from prose_preprocessing_util.ir import ProseBlock, ProseDocument

import chunk_and_embed as ce
from rag.retriever.schemas import ProseChunk


def _doc(
    *,
    doc_id: str = "rst/demo.rst",
    source: str = "official_doc",
    source_file: str = "demo.rst",
    match_tokens: list[str] | None = None,
    blocks: list[ProseBlock],
    keep: bool = True,
) -> ProseDocument:
    return ProseDocument(
        doc_id=doc_id,
        source=source,
        source_file=source_file,
        source_type="rst",
        since_version="4.0",
        keep=keep,
        match_tokens=match_tokens or ["await"],
        blocks=blocks,
    )


def test_lift_prose_jsonl_type_a(tmp_path: Path) -> None:
    path = tmp_path / "upgrading_to_godot_4.1.rst.prose.jsonl"
    rec = {
        "heading_path": ["Upgrading from Godot 4.0 to Godot 4.1", "Breaking changes"],
        "text": "The GDExtension API completely breaks compatibility in 4.1.",
        "since_version": "4.1",
        "source_file": "upgrading_to_godot_4.1.rst",
        "source": "official_prose",
    }
    path.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    docs = ce.lift_prose_jsonl(path)
    assert len(docs) == 1
    doc = docs[0]
    assert doc.source_type == "legacy_prose_jsonl"
    assert doc.source == "official_prose"
    assert doc.since_version == "4.1"
    assert doc.blocks[0].type == "paragraph"
    assert "Breaking changes" in doc.doc_id


def test_chunker_skips_headings_and_packs_same_path() -> None:
    doc = _doc(
        blocks=[
            ProseBlock(block_id="b0001", type="heading", text="Annotations", heading_path=["GDScript"]),
            ProseBlock(
                block_id="b0002",
                type="paragraph",
                text="Annotations are extra information given to the interpreter.",
                heading_path=["GDScript", "Annotations"],
            ),
            ProseBlock(
                block_id="b0003",
                type="code",
                text="@export var speed := 0",
                heading_path=["GDScript", "Annotations"],
            ),
        ]
    )
    chunks = ce.chunk_documents([doc])
    assert len(chunks) == 1
    assert chunks[0].heading_path == ["GDScript", "Annotations"]
    assert "Annotations are extra" in chunks[0].text
    assert "@export var speed" in chunks[0].text
    # Body only: heading prefix is for embedding, not ProseChunk.text.
    assert not chunks[0].text.startswith("GDScript")
    assert "await" in chunks[0].related_symbols
    assert chunks[0].since_version_code == 40000


def test_chunker_does_not_split_code_across_chunks() -> None:
    # Force tiny token budget so packing has to choose: keep code whole.
    code = "func _ready():\n    print('hello')\n    print('world')\n    print('again')"
    prose = "Explanation of the example that sits right before the code sample."
    doc = _doc(
        blocks=[
            ProseBlock(block_id="b0001", type="paragraph", text=prose, heading_path=["Demo"]),
            ProseBlock(block_id="b0002", type="code", text=code, heading_path=["Demo"]),
        ]
    )

    def counter(text: str) -> int:
        # Count words; the combined embedding text of prose+code is large,
        # each piece alone is small.
        return len(text.split())

    chunks = ce.chunk_documents([doc], token_counter=counter, max_tokens=20, target_tokens=12)
    code_chunks = [c for c in chunks if "print('hello')" in c.text]
    assert code_chunks, chunks
    for chunk in code_chunks:
        assert "print('hello')" in chunk.text
        assert "print('again')" in chunk.text


def test_chunker_drops_short_official_keeps_long() -> None:
    doc = _doc(
        blocks=[
            ProseBlock(block_id="b0001", type="paragraph", text="too short", heading_path=["X"]),
            ProseBlock(
                block_id="b0002",
                type="paragraph",
                text="This official paragraph is long enough to survive the twenty-character floor.",
                heading_path=["X"],
            ),
        ]
    )
    chunks = ce.chunk_documents([doc])
    assert len(chunks) == 1
    assert "twenty-character floor" in chunks[0].text


def test_chunker_community_floor_is_80() -> None:
    doc = _doc(
        source="community_prose",
        blocks=[
            ProseBlock(
                block_id="b0001",
                type="paragraph",
                text="A community blurb that is longer than twenty but shorter than eighty chars.",
                heading_path=["Blog"],
            )
        ],
    )
    assert ce.chunk_documents([doc]) == []


def test_chunker_skips_keep_false() -> None:
    doc = _doc(
        keep=False,
        blocks=[
            ProseBlock(
                block_id="b0001",
                type="paragraph",
                text="This would be a perfectly packable paragraph about await.",
                heading_path=["X"],
            )
        ],
    )
    assert ce.chunk_documents([doc]) == []


def test_chunk_ids_are_stable_across_two_runs() -> None:
    doc = _doc(
        blocks=[
            ProseBlock(
                block_id="b0001",
                type="paragraph",
                text="First packed paragraph about Tween fire-and-forget objects in Godot 4.",
                heading_path=["Tween"],
            ),
            ProseBlock(
                block_id="b0002",
                type="paragraph",
                text="Second packed paragraph about create_tween replacing the old Tween node.",
                heading_path=["Tween"],
            ),
        ]
    )
    first = {c.id for c in ce.chunk_documents([doc])}
    second = {c.id for c in ce.chunk_documents([doc])}
    assert first == second
    assert first  # not empty


def test_hard_split_respects_max_tokens() -> None:
    # One enormous paragraph, no newlines. Binary-search split must emit
    # pieces whose embedding_text is <= max_tokens.
    text = "await " * 400
    doc = _doc(
        blocks=[ProseBlock(block_id="b0001", type="paragraph", text=text, heading_path=["Await"])]
    )
    chunks = ce.chunk_documents([doc], max_tokens=40, target_tokens=30)
    assert len(chunks) >= 2
    for chunk in chunks:
        n = ce.count_tokens(ce.embedding_text(chunk.heading_path, chunk.text))
        assert n <= 40


def test_prose_chunk_schema_fills_version_code() -> None:
    chunk = ProseChunk(
        id="x::c0001",
        text="body",
        heading_path=["A"],
        since_version="4.7.1",
        source="official_doc",
        source_file="demo.rst",
    )
    assert chunk.since_version_code == 40701
