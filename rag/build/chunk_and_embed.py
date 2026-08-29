"""Stage 4: chunk all Document IR and build embeddings in the LanceDB corpus.

This script runs in two internal sub-stages:
  1. Chunk phase: IR -> ProseChunk list.
  2. Embed phase: ProseChunk -> vectors -> artifacts/corpus.lance.

Design reference: rag/vault/tier_b_prose/CHUNKING.md §8
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path

# Add workspace root so we can import rag.retriever.schemas if needed.
_BUILD_DIR = Path(__file__).resolve().parent
if str(_BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(_BUILD_DIR))
_RAG_ROOT = _BUILD_DIR.parent
_WORKSPACE = _RAG_ROOT.parent
if str(_WORKSPACE) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE))

from prose_preprocessing_util.ir import (  # noqa: E402
    ProseBlock,
    ProseDocument,
    read_ir,
)
from rag.retriever.schemas import ProseChunk  # noqa: E402
from rag.version_codec import version_to_code  # noqa: E402

TIER_B_PROSE_DIR = Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose"
IR_DIR = TIER_B_PROSE_DIR / "ir"
TYPE_A_DIR = TIER_B_PROSE_DIR / "_raw" / "official_upgrading_guide"
CORPUS_PATH = Path(__file__).resolve().parent.parent / "artifacts" / "corpus.lance"

# Embedding model: BAAI/bge-small-en-v1.5, 384 dims, max 512 tokens.
# This model is English-first. Agent retrieval works best when the query
# contains English symbol names / error text (see CHUNKING.md §8.1).
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
TARGET_TOKENS = 360
MAX_TOKENS = 480

_BACKTICK_RE = re.compile(r"`([^`]+)`")
_TOKEN_RE = re.compile(r"\w+|[^\s\w]")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

TokenCounter = Callable[[str], int]


def count_tokens(text: str) -> int:
    """Approximate WordPiece length; good enough to stay under the 512 cap."""
    if not text.strip():
        return 0
    return max(1, len(_TOKEN_RE.findall(text)))


def embedding_text(heading_path: list[str], body: str) -> str:
    if heading_path:
        return " > ".join(heading_path) + "\n\n" + body
    return body


def lift_prose_jsonl(path: Path) -> list[ProseDocument]:
    """Lift type-A ``*.prose.jsonl`` into degenerate ProseDocuments (§3.6)."""
    docs: list[ProseDocument] = []
    seen: dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        rec = json.loads(raw)
        heading_path = list(rec.get("heading_path") or [])
        source_file = str(rec.get("source_file") or path.name)
        source = str(rec.get("source") or "official_prose")
        path_key = "/".join(heading_path)
        doc_id = f"legacy_prose_jsonl/{source_file}#{path_key}"
        if doc_id in seen:
            seen[doc_id] += 1
            doc_id = f"{doc_id}#{seen[doc_id]}"
        else:
            seen[doc_id] = 1
        text = str(rec.get("text") or "")
        docs.append(
            ProseDocument(
                schema_version=1,
                doc_id=doc_id,
                source=source,
                source_file=source_file,
                source_url=None,
                source_type="legacy_prose_jsonl",
                since_version=rec.get("since_version"),
                confidence="verified",
                title=None,
                keep=True,
                match_tokens=[],
                blocks=[
                    ProseBlock(
                        block_id="b0001",
                        type="paragraph",
                        text=text,
                        heading_path=heading_path,
                    )
                ],
            )
        )
    return docs


def load_ir_documents() -> list[ProseDocument]:
    """Recursively read ``ir/<bucket>/*.ir.json`` where ``keep=true``."""
    docs: list[ProseDocument] = []
    if not IR_DIR.is_dir():
        return docs
    for path in sorted(IR_DIR.rglob("*.ir.json")):
        doc = read_ir(path)
        if doc.keep:
            docs.append(doc)
    return docs


def _min_body_chars(source: str) -> int:
    if source == "community_prose":
        return 80
    return 20


def _related_symbols(body: str, match_tokens: list[str]) -> list[str]:
    found: list[str] = []
    for match in _BACKTICK_RE.findall(body):
        tok = match.strip()
        if tok and tok not in found:
            found.append(tok)
    for tok in match_tokens:
        if tok and tok not in found:
            found.append(tok)
    return found


def _chunk_one(
    doc: ProseDocument,
    counter: TokenCounter,
    target_tokens: int,
    max_tokens: int,
) -> list[ProseChunk]:
    stream = [b for b in doc.blocks if b.type != "heading"]
    groups: list[tuple[tuple[str, ...], list[ProseBlock]]] = []
    for block in stream:
        key = tuple(block.heading_path)
        if not groups or groups[-1][0] != key:
            groups.append((key, [block]))
        else:
            groups[-1][1].append(block)

    packed: list[tuple[list[str], str]] = []
    for heading, blocks in groups:
        packed.extend(
            _pack_group(list(heading), blocks, counter, target_tokens, max_tokens)
        )

    min_chars = _min_body_chars(doc.source)
    chunks: list[ProseChunk] = []
    n = 0
    for heading_path, body in packed:
        if len(body.strip()) < min_chars:
            continue
        n += 1
        chunks.append(
            ProseChunk(
                id=f"{doc.doc_id}::c{n:04d}",
                text=body,
                heading_path=heading_path,
                since_version=doc.since_version,
                since_version_code=version_to_code(doc.since_version),
                related_symbols=_related_symbols(body, doc.match_tokens),
                source=doc.source,
                source_file=doc.source_file,
                source_url=doc.source_url,
            )
        )
    return chunks


def _pack_group(
    heading_path: list[str],
    blocks: list[ProseBlock],
    counter: TokenCounter,
    target_tokens: int,
    max_tokens: int,
) -> list[tuple[list[str], str]]:
    out: list[tuple[list[str], str]] = []
    current: list[str] = []

    def fits(parts: list[str]) -> bool:
        body = "\n\n".join(parts)
        return counter(embedding_text(heading_path, body)) <= max_tokens

    def flush() -> None:
        if current:
            out.append((heading_path, "\n\n".join(current)))
            current.clear()

    for block in blocks:
        piece = block.text.strip()
        if not piece:
            continue
        candidate = current + [piece]
        if fits(candidate):
            current.append(piece)
            continue
        # Overflow: flush what we have, then try the block alone.
        flush()
        if fits([piece]):
            current.append(piece)
            continue
        # Single block still over the cap: hard-split.
        out.extend(_hard_split(heading_path, piece, counter, max_tokens))

    flush()
    # Merge a trailing undersized prose chunk into the previous one when the
    # previous one still has room (keeps "说明 + 紧随 code" together if we
    # flushed too early). target_tokens is a soft goal, not a flush trigger.
    _ = target_tokens  # reserved for future soft-flush heuristics
    return out


def _hard_split(
    heading_path: list[str],
    text: str,
    counter: TokenCounter,
    max_tokens: int,
) -> list[tuple[list[str], str]]:
    parts: list[str] = []
    paragraphs = re.split(r"\n\s*\n", text)
    units: list[str] = []
    for para in paragraphs:
        if counter(embedding_text(heading_path, para)) <= max_tokens:
            units.append(para.strip())
            continue
        sentences = _SENTENCE_RE.split(para.strip())
        for sent in sentences:
            if counter(embedding_text(heading_path, sent)) <= max_tokens:
                units.append(sent.strip())
                continue
            units.extend(_split_chars(heading_path, sent, counter, max_tokens))

    current: list[str] = []

    def fits(parts_: list[str]) -> bool:
        return counter(embedding_text(heading_path, "\n\n".join(parts_))) <= max_tokens

    for unit in units:
        if not unit:
            continue
        cand = current + [unit]
        if fits(cand):
            current.append(unit)
        else:
            if current:
                parts.append("\n\n".join(current))
            current = [unit]
    if current:
        parts.append("\n\n".join(current))
    return [(heading_path, p) for p in parts if p.strip()]


def _split_chars(
    heading_path: list[str],
    text: str,
    counter: TokenCounter,
    max_tokens: int,
) -> list[str]:
    # Last-resort character window. Prefix tokens are counted each time.
    out: list[str] = []
    remaining = text
    while remaining:
        lo, hi = 1, len(remaining)
        best = 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if counter(embedding_text(heading_path, remaining[:mid])) <= max_tokens:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        out.append(remaining[:best].strip())
        remaining = remaining[best:]
    return [p for p in out if p]


def chunk_documents(
    docs: list[ProseDocument],
    *,
    token_counter: TokenCounter | None = None,
    target_tokens: int = TARGET_TOKENS,
    max_tokens: int = MAX_TOKENS,
) -> list[ProseChunk]:
    """Single chunker: heading_path packing, code-atomic, 480-token cap."""
    counter = token_counter or count_tokens
    chunks: list[ProseChunk] = []
    for doc in docs:
        if not doc.keep:
            continue
        chunks.extend(_chunk_one(doc, counter, target_tokens, max_tokens))
    return chunks


def embed_chunks(chunks: list) -> list[dict]:
    """Embed ProseChunk records with fastembed / bge-small-en-v1.5."""
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "fastembed is required for embedding. uv sync --group build"
        ) from exc

    model = TextEmbedding(model_name=EMBEDDING_MODEL)
    texts = [embedding_text(c.heading_path, c.text) for c in chunks]
    vectors = list(model.embed(texts))
    records: list[dict] = []
    for chunk, vec in zip(chunks, vectors, strict=True):
        vector = [float(x) for x in vec]
        if len(vector) != EMBEDDING_DIM:
            raise RuntimeError(
                f"expected {EMBEDDING_DIM}-d vector, got {len(vector)} for {chunk.id}"
            )
        records.append(
            {
                "id": chunk.id,
                "vector": vector,
                "text": chunk.text,
                "heading_path": chunk.heading_path,
                "since_version": chunk.since_version,
                "since_version_code": chunk.since_version_code,
                "related_symbols": chunk.related_symbols,
                "source": chunk.source,
                "source_file": chunk.source_file,
                "source_url": chunk.source_url,
            }
        )
    return records


def write_corpus(records: list[dict]) -> None:
    """Write records to artifacts/corpus.lance (rebuild for idempotency)."""
    import lancedb

    CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(CORPUS_PATH.parent))
    if "corpus" in db.table_names():
        db.drop_table("corpus")
    db.create_table("corpus", data=records, mode="overwrite")


def _type_a_paths() -> list[Path]:
    paths: list[Path] = []
    if TYPE_A_DIR.is_dir():
        paths.extend(sorted(TYPE_A_DIR.glob("*.prose.jsonl")))
    # Historical location from the A-layer compile (vault/tier_b_prose/*.prose.jsonl).
    paths.extend(sorted(TIER_B_PROSE_DIR.glob("*.prose.jsonl")))
    # De-dupe by filename, preferring TYPE_A_DIR.
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        if path.name in seen:
            continue
        seen.add(path.name)
        unique.append(path)
    return unique


def main() -> int:
    """Load IR + type A, chunk, embed, and write corpus.lance."""
    docs: list[ProseDocument] = []
    for path in _type_a_paths():
        lifted = lift_prose_jsonl(path)
        print(f"  lift {path.name}: {len(lifted)} degenerate docs")
        docs.extend(lifted)
    ir_docs = load_ir_documents()
    print(f"  ir documents: {len(ir_docs)}")
    docs.extend(ir_docs)
    chunks = chunk_documents(docs)
    print(f"chunked {len(chunks)} chunks from {len(docs)} docs")
    skip = (
        "--skip-embed" in sys.argv
        or os.environ.get("TIER_B_SKIP_EMBED", "").strip() in {"1", "true", "yes"}
    )
    if skip:
        print("skip embed (TIER_B_SKIP_EMBED / --skip-embed)")
        return 0
    if not chunks:
        print("no chunks to embed", file=sys.stderr)
        return 1
    records = embed_chunks(chunks)
    write_corpus(records)
    print(f"wrote {len(records)} rows -> {CORPUS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
