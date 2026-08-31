"""Tests for the heading-pack chunker in ``prose_preprocessing_util.chunker``.

默认单测注入 ``approx_token_count`` / 假计数器，**不加载** ONNX。
生产切块与 embedding 见::

    uv run python build/chunk_prose.py --strategy-id default
    uv run python build/embed_prose.py --strategy-id default
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prose_preprocessing_util.chunker import (
    ChunkConfig,
    approx_token_count,
    chunk_documents,
    embedding_text,
    lift_prose_jsonl,
    split_code_at_functions,
)
from prose_preprocessing_util.ir import ProseBlock, ProseDocument

from rag.retriever.schemas import ProseChunk

import chunk_prose


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
    docs = lift_prose_jsonl(path)
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
    chunks = chunk_documents([doc])
    assert len(chunks) == 1
    assert chunks[0].heading_path == ["GDScript", "Annotations"]
    assert "Annotations are extra" in chunks[0].text
    assert "@export var speed" in chunks[0].text
    assert not chunks[0].text.startswith("GDScript")
    assert "await" in chunks[0].related_symbols
    assert chunks[0].since_version_code == 40000


def test_chunker_keeps_prose_and_following_code_together() -> None:
    prose = "Explanation of the example that sits right before the code sample."
    code = "func _ready():\n    print('hello')\n    print('world')"
    doc = _doc(
        blocks=[
            ProseBlock(block_id="b0001", type="paragraph", text=prose, heading_path=["Demo"]),
            ProseBlock(block_id="b0002", type="code", text=code, heading_path=["Demo"]),
        ]
    )
    chunks = chunk_documents([doc])
    assert len(chunks) == 1
    assert prose in chunks[0].text
    assert "print('hello')" in chunks[0].text


def test_chunker_does_not_split_code_across_chunks() -> None:
    code = "func _ready():\n    print('hello')\n    print('world')\n    print('again')"
    prose = "Explanation of the example that sits right before the code sample."
    doc = _doc(
        blocks=[
            ProseBlock(block_id="b0001", type="paragraph", text=prose, heading_path=["Demo"]),
            ProseBlock(block_id="b0002", type="code", text=code, heading_path=["Demo"]),
        ]
    )

    def counter(text: str) -> int:
        return len(text.split())

    chunks = chunk_documents([doc], token_counter=counter, max_tokens=20, target_tokens=12)
    code_chunks = [c for c in chunks if "print('hello')" in c.text]
    assert code_chunks, chunks
    for chunk in code_chunks:
        assert "print('hello')" in chunk.text
        assert "print('again')" in chunk.text


def test_split_code_at_function_boundaries() -> None:
    code = (
        "func alpha():\n    print('a')\n    print('aa')\n"
        "func beta():\n    print('b')\n    print('bb')\n"
    )
    units = split_code_at_functions(code)
    assert len(units) == 2
    assert units[0].startswith("func alpha")
    assert "print('b')" not in units[0]
    assert units[1].startswith("func beta")
    assert "print('a')" not in units[1]


def test_oversized_multi_func_code_splits_on_func_not_mid_body() -> None:
    func_a = "func alpha():\n    " + "print('a')\n    " * 40
    func_b = "func beta():\n    " + "print('b')\n    " * 40
    doc = _doc(
        blocks=[
            ProseBlock(block_id="b0001", type="code", text=func_a + func_b, heading_path=["Demo"]),
        ]
    )
    chunks = chunk_documents([doc], max_tokens=80, target_tokens=40)
    bodies = [c.text for c in chunks]
    joined = "\n".join(bodies)
    assert "func alpha" in joined
    assert "func beta" in joined
    for body in bodies:
        if "func alpha" in body and "func beta" in body:
            continue
        if "func alpha" in body:
            assert "func beta" not in body
            assert "print('b')" not in body
        if "func beta" in body:
            assert "func alpha" not in body


def test_overlap_zero_does_not_prefix_next_chunk() -> None:
    doc = _doc(
        blocks=[
            ProseBlock(
                block_id="b0001",
                type="paragraph",
                text=("ALPHA unique packing sentence goes here. " * 5),
                heading_path=["Tween"],
            ),
            ProseBlock(
                block_id="b0002",
                type="paragraph",
                text=("BETA unique packing sentence goes here. " * 5),
                heading_path=["Tween"],
            ),
        ]
    )
    chunks = chunk_documents([doc], max_tokens=55, target_tokens=40, overlap=0)
    beta = [c for c in chunks if "BETA" in c.text]
    assert beta
    for chunk in beta:
        assert not chunk.text.strip().startswith("ALPHA unique")


def test_overlap_stops_at_code_and_does_not_copy_code() -> None:
    doc = _doc(
        blocks=[
            ProseBlock(
                block_id="b0001",
                type="paragraph",
                text=("ALPHA unique packing sentence goes here. " * 5),
                heading_path=["Demo"],
            ),
            ProseBlock(
                block_id="b0002",
                type="code",
                text="func alpha():\n    print('KEEP_ATOMIC')",
                heading_path=["Demo"],
            ),
            ProseBlock(
                block_id="b0003",
                type="paragraph",
                text=("BETA unique packing sentence goes here. " * 5),
                heading_path=["Demo"],
            ),
        ]
    )
    chunks = chunk_documents([doc], max_tokens=55, target_tokens=40, overlap=12)
    beta = next(c for c in chunks if "BETA" in c.text)
    assert "KEEP_ATOMIC" not in beta.text
    assert "func alpha" not in beta.text


def test_overlap_copies_trailing_prose_only() -> None:
    doc = _doc(
        blocks=[
            ProseBlock(
                block_id="b0001",
                type="paragraph",
                text=("ALPHA unique packing sentence goes here. " * 5),
                heading_path=["Tween"],
            ),
            ProseBlock(
                block_id="b0002",
                type="paragraph",
                text=("BETA unique packing sentence goes here. " * 5),
                heading_path=["Tween"],
            ),
        ]
    )
    zero = chunk_documents([doc], max_tokens=55, target_tokens=40, overlap=0)
    overlapped = chunk_documents([doc], max_tokens=55, target_tokens=40, overlap=12)
    beta_zero = next(c for c in zero if "BETA" in c.text)
    beta_ov = next(c for c in overlapped if "BETA" in c.text)
    assert "ALPHA" not in beta_zero.text
    assert "ALPHA" in beta_ov.text
    assert "BETA" in beta_ov.text


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
    chunks = chunk_documents([doc])
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
    assert chunk_documents([doc]) == []


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
    assert chunk_documents([doc]) == []


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
    first = {c.id for c in chunk_documents([doc])}
    second = {c.id for c in chunk_documents([doc])}
    assert first == second
    assert first


def test_hard_split_respects_max_tokens() -> None:
    text = "await " * 400
    doc = _doc(
        blocks=[ProseBlock(block_id="b0001", type="paragraph", text=text, heading_path=["Await"])]
    )
    chunks = chunk_documents([doc], max_tokens=40, target_tokens=30)
    assert len(chunks) >= 2
    for chunk in chunks:
        n = approx_token_count(embedding_text(chunk.heading_path, chunk.text))
        assert n <= 40


def test_chunks_jsonl_roundtrip(tmp_path: Path) -> None:
    doc = _doc(
        blocks=[
            ProseBlock(
                block_id="b0001",
                type="paragraph",
                text="Awaiting a signal returns control to the caller until it emits.",
                heading_path=["Await"],
            )
        ]
    )
    chunks = chunk_documents([doc])
    dest = tmp_path / "default"
    chunk_prose.write_chunks(
        chunks,
        dest,
        ChunkConfig().to_manifest(strategy_id="default", chunk_count=len(chunks)),
    )
    loaded = chunk_prose.read_chunks_jsonl(dest / "chunks.jsonl")
    assert len(loaded) == len(chunks)
    assert loaded[0].id == chunks[0].id
    assert loaded[0].text == chunks[0].text
    assert loaded[0].heading_path == chunks[0].heading_path
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["strategy_id"] == "default"
    assert manifest["overlap"] == 0
    assert manifest["chunk_size"] == 0
    assert manifest["tokenizer"] == "BAAI/bge-small-en-v1.5"


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


def _fastembed_available() -> bool:
    try:
        import fastembed  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.skipif(not _fastembed_available(), reason="fastembed not installed")
def test_bge_token_count_runs() -> None:
    from prose_preprocessing_util.bge import bge_token_count

    n = bge_token_count("create_tween await get_tree")
    assert n >= 3
    assert bge_token_count("") == 0
    assert bge_token_count("   ") == 0
