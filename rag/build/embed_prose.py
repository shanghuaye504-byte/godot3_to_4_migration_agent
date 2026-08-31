"""阶段 4b：``artifacts/chunks/<strategy_id>/chunks.jsonl`` → LanceDB。

不重新切块。切块见 ``chunk_prose.py``。
协议：``CHUNKING.md`` §11、``rag/retriever/README.md`` §4。

本表向量空间是 **passage**。建库必须 ``passage_embed(embedding_text)``；
检索必须对 query 字符串走 ``query_embed``。禁止对这份 corpus 使用
``embed()``，禁止与 ``passage_embed`` 混用。

输入
----
- ``artifacts/chunks/<id>/chunks.jsonl``
- 同目录 ``manifest.json``（若存在，会复制到 corpora 并补 ``corpus_path``）

输出
----
::

    artifacts/corpora/<strategy_id>/corpus.lance
    artifacts/corpora/<strategy_id>/manifest.json

仅 ``strategy_id=default`` 且未指定 ``--out`` 时，再镜像一份到
``artifacts/corpus.lance``（兼容旧路径）。其它策略不碰这条路径。

用法（在 ``rag/`` 下；需 ``uv sync --group build`` + ``FASTEMBED_CACHE_PATH``）
--------------------------------------------------------------------------
::

    uv run python build/embed_prose.py --strategy-id default

CLI
---
- ``--strategy-id``  读 chunks/<id>/，写 corpora/<id>/（默认 default）
- ``--chunks``       覆盖 chunks.jsonl 路径
- ``--out``          覆盖 LanceDB 目录（传入时不再镜像旧路径）
- ``--model``        默认 ``BAAI/bge-small-en-v1.5``

512 token 截断用同一套 WordPiece（``bge_token_count``），只截断送进模型的
字符串，不改 ``chunks.jsonl`` / Lance 的 ``text``。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import warnings
from pathlib import Path

_BUILD_DIR = Path(__file__).resolve().parent
if str(_BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(_BUILD_DIR))
_RAG_ROOT = _BUILD_DIR.parent
_WORKSPACE = _RAG_ROOT.parent
if str(_WORKSPACE) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE))

from prose_preprocessing_util.bge import bge_token_count, get_text_embedding  # noqa: E402
from prose_preprocessing_util.chunker import (  # noqa: E402
    DEFAULT_STRATEGY_ID,
    EMBED_HARD_CAP,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    embedding_text,
)
from rag.retriever.schemas import ProseChunk  # noqa: E402

ARTIFACTS_DIR = _RAG_ROOT / "artifacts"
LEGACY_CORPUS = ARTIFACTS_DIR / "corpus.lance"


def chunks_dir(strategy_id: str) -> Path:
    return ARTIFACTS_DIR / "chunks" / strategy_id


def corpora_dir(strategy_id: str) -> Path:
    return ARTIFACTS_DIR / "corpora" / strategy_id


def read_chunks_jsonl(path: Path) -> list[ProseChunk]:
    chunks: list[ProseChunk] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        chunks.append(ProseChunk.model_validate_json(line))
    return chunks


def _truncate_for_embed(chunk: ProseChunk) -> str:
    """Keep embedding_text under the model cap; never rewrite the stored body."""
    text = embedding_text(chunk.heading_path, chunk.text)
    if bge_token_count(text) <= EMBED_HARD_CAP:
        return text
    warnings.warn(
        f"embedding text for {chunk.id} exceeds {EMBED_HARD_CAP} tokens; "
        "truncating for the model only (chunks.jsonl is unchanged)",
        stacklevel=2,
    )
    body = chunk.text
    lo, hi = 0, len(body)
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = embedding_text(chunk.heading_path, body[:mid])
        if bge_token_count(cand) <= EMBED_HARD_CAP:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return embedding_text(chunk.heading_path, body[:best])


def embed_chunks(chunks: list[ProseChunk], model_name: str = EMBEDDING_MODEL) -> list[dict]:
    """用 ``passage_embed`` 给 ProseChunk 出向量（bge-small-en-v1.5）。

    检索必须配对 ``query_embed``。超 512 WordPiece 只截断送进模型，
    不改 jsonl / Lance 里的 body。
    """
    model = get_text_embedding(model_name)
    texts = [_truncate_for_embed(c) for c in chunks]
    vectors = list(model.passage_embed(texts))
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


def write_corpus(records: list[dict], dest_dir: Path) -> Path:
    """把记录写成表 ``corpus``（整表重建，保证幂等）。LanceDB 只存向量，不调模型。"""
    import lancedb

    dest_dir.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(dest_dir))
    if "corpus" in db.table_names():
        db.drop_table("corpus")
    db.create_table("corpus", data=records, mode="overwrite")
    table = db.open_table("corpus")
    try:
        from lancedb.index import FTS

        table.create_index("text", config=FTS())
    except Exception as exc:
        warnings.warn(f"未能在建库时创建 FTS 索引（检索侧会在首次 BM25 查询时补建）: {exc}")
    return dest_dir / "corpus.lance"


def _mirror_legacy_corpus(src: Path) -> None:
    """Copy default strategy table to artifacts/corpus.lance for old paths."""
    if LEGACY_CORPUS.exists():
        if LEGACY_CORPUS.is_dir():
            shutil.rmtree(LEGACY_CORPUS)
        else:
            LEGACY_CORPUS.unlink()
    if src.is_dir():
        shutil.copytree(src, LEGACY_CORPUS)
    else:
        shutil.copy2(src, LEGACY_CORPUS)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把 chunks.jsonl 嵌入为 LanceDB corpus（不重新切块）。"
    )
    parser.add_argument(
        "--strategy-id",
        default=DEFAULT_STRATEGY_ID,
        help="读 artifacts/chunks/<id>/，写 artifacts/corpora/<id>/",
    )
    parser.add_argument(
        "--chunks",
        type=Path,
        default=None,
        help="覆盖 chunks.jsonl 路径",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="覆盖 LanceDB 目录（传入则不再镜像 artifacts/corpus.lance）",
    )
    parser.add_argument(
        "--model",
        default=EMBEDDING_MODEL,
        help=f"fastembed 模型名（默认 {EMBEDDING_MODEL}）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    jsonl = args.chunks or (chunks_dir(args.strategy_id) / "chunks.jsonl")
    if not jsonl.is_file():
        print(f"chunks file not found: {jsonl}", file=sys.stderr)
        print("Run chunk_prose.py first.", file=sys.stderr)
        return 1
    dest = args.out or corpora_dir(args.strategy_id)
    chunks = read_chunks_jsonl(jsonl)
    print(f"  loaded {len(chunks)} chunks from {jsonl}")
    if not chunks:
        print("no chunks to embed", file=sys.stderr)
        return 1
    records = embed_chunks(chunks, model_name=args.model)
    lance_path = write_corpus(records, dest)
    print(f"wrote {len(records)} rows -> {lance_path}")
    if args.strategy_id == DEFAULT_STRATEGY_ID and args.out is None:
        _mirror_legacy_corpus(lance_path)
        print(f"mirrored default corpus -> {LEGACY_CORPUS}")
    manifest_src = jsonl.parent / "manifest.json"
    if manifest_src.is_file():
        payload = json.loads(manifest_src.read_text(encoding="utf-8"))
        payload["corpus_path"] = str(lance_path)
        payload["embedding_api"] = "passage_embed"
        payload["query_api"] = "query_embed"
        (dest / "manifest.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
