"""阶段 4a：IR + 类型 A jsonl → ``artifacts/chunks/<strategy_id>/``。

不调用 embedding 模型。向量写入见 ``embed_prose.py``。
装箱算法见 ``prose_preprocessing_util.chunker`` 模块 docstring 与
``rag/vault/tier_b_prose/CHUNKING.md`` §8。

输入
----
- ``vault/tier_b_prose/ir/**/*.ir.json`` 中 ``keep=true`` 的文档
- ``vault/tier_b_prose/_raw/official_upgrading_guide/*.prose.jsonl``
  （类型 A，lift 成退化 IR，不写 ``.ir.json``）

输出
----
::

    artifacts/chunks/<strategy_id>/
      chunks.jsonl     # 每行一个 ProseChunk（无 vector）
      manifest.json    # 切块参数 + chunk_count，供对比实验复现

用法（在 ``rag/`` 下；需 ``uv sync --group build`` + ``FASTEMBED_CACHE_PATH``）
------------------------------------------------------------------------------
::

    uv run python build/chunk_prose.py --strategy-id default

装箱用 bge-small 的 WordPiece（``bge_token_count``），与 ``embed_prose.py``
同一套 tokenizer。缺 fastembed 时直接失败，不回退正则。

换策略只改 CLI 和 ``--strategy-id``，不必重跑 IR::

    uv run python build/chunk_prose.py --strategy-id heading_ov64 --overlap 64

CLI 参数（第一次跑用默认值）
----------------------------
- ``--strategy-id``  输出目录名，默认 ``default``
- ``--mode``         ``heading``（默认，按 heading_path 装箱）或 ``fixed``
- ``--chunk-size``   固定窗 token 数，默认 0=关闭；``fixed`` 模式必须 >0
- ``--overlap``      相邻 chunk 重叠的 prose token，默认 0
- ``--max-tokens``   硬上限，默认 480
- ``--target-tokens`` 软目标，默认 360
- ``--min-chars-official`` / ``--min-chars-community``  过短 body 丢弃，默认 20 / 80
- ``--code-attach``  目前只有 ``preceding``
- ``--code-split``   目前只有 ``function``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BUILD_DIR = Path(__file__).resolve().parent
if str(_BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(_BUILD_DIR))
_RAG_ROOT = _BUILD_DIR.parent
_WORKSPACE = _RAG_ROOT.parent
if str(_WORKSPACE) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE))

from prose_preprocessing_util.bge import bge_token_count  # noqa: E402
from prose_preprocessing_util.chunker import (  # noqa: E402
    DEFAULT_STRATEGY_ID,
    MAX_TOKENS,
    TARGET_TOKENS,
    ChunkConfig,
    chunk_documents,
    lift_prose_jsonl,
    load_ir_documents,
    type_a_paths,
)
from rag.retriever.schemas import ProseChunk  # noqa: E402

TIER_B_PROSE_DIR = _RAG_ROOT / "vault" / "tier_b_prose"
ARTIFACTS_DIR = _RAG_ROOT / "artifacts"


def chunks_dir(strategy_id: str) -> Path:
    return ARTIFACTS_DIR / "chunks" / strategy_id


def write_chunks(chunks: list[ProseChunk], dest_dir: Path, manifest: dict) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    jsonl = dest_dir / "chunks.jsonl"
    with jsonl.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(chunk.model_dump_json() + "\n")
    (dest_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_chunks_jsonl(path: Path) -> list[ProseChunk]:
    chunks: list[ProseChunk] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        chunks.append(ProseChunk.model_validate_json(line))
    return chunks


def load_all_documents() -> list:
    docs = []
    for path in type_a_paths(TIER_B_PROSE_DIR):
        lifted = lift_prose_jsonl(path)
        print(f"  lift {path.name}: {len(lifted)} degenerate docs")
        docs.extend(lifted)
    ir_docs = load_ir_documents(TIER_B_PROSE_DIR / "ir")
    print(f"  ir documents: {len(ir_docs)}")
    docs.extend(ir_docs)
    return docs


def build_config(args: argparse.Namespace) -> ChunkConfig:
    return ChunkConfig(
        mode=args.mode,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        max_tokens=args.max_tokens,
        target_tokens=args.target_tokens,
        min_chars_official=args.min_chars_official,
        min_chars_community=args.min_chars_community,
        code_attach=args.code_attach,
        code_split=args.code_split,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把 Document IR 装箱成 chunks.jsonl（不调用 embedding 模型）。"
    )
    parser.add_argument(
        "--strategy-id",
        default=DEFAULT_STRATEGY_ID,
        help="输出目录名，写到 artifacts/chunks/<id>/（默认 default）",
    )
    parser.add_argument(
        "--mode",
        choices=("heading", "fixed"),
        default="heading",
        help="heading=按 heading_path 装箱；fixed=纯 prose 再按 --chunk-size 开窗",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=0,
        help="固定窗 token 数；0 表示关闭（默认）。fixed 模式必须 >0",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=0,
        help="相邻 chunk 重叠的 prose token；0 表示不 overlap（默认）",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=MAX_TOKENS,
        help="embedding 文本（标题前缀 + body）硬上限（默认 480）",
    )
    parser.add_argument(
        "--target-tokens",
        type=int,
        default=TARGET_TOKENS,
        help="软目标：尽量装满，未到 --max-tokens 不主动切（默认 360）",
    )
    parser.add_argument(
        "--min-chars-official",
        type=int,
        default=20,
        help="官方源过短 body 丢弃（默认 20）",
    )
    parser.add_argument(
        "--min-chars-community",
        type=int,
        default=80,
        help="社区源过短 body 丢弃（默认 80）",
    )
    parser.add_argument(
        "--code-attach",
        choices=("preceding",),
        default="preceding",
        help="代码与紧邻前文说明绑成一捆（目前只有 preceding）",
    )
    parser.add_argument(
        "--code-split",
        choices=("function",),
        default="function",
        help="超限时按 func/class/enum 边界切代码（目前只有 function）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mode == "fixed" and args.chunk_size <= 0:
        print("fixed mode requires --chunk-size > 0", file=sys.stderr)
        return 2
    config = build_config(args)
    docs = load_all_documents()
    chunks = chunk_documents(docs, config=config, token_counter=bge_token_count)
    dest = chunks_dir(args.strategy_id)
    manifest = config.to_manifest(strategy_id=args.strategy_id, chunk_count=len(chunks))
    write_chunks(chunks, dest, manifest)
    print(f"chunked {len(chunks)} chunks from {len(docs)} docs")
    print(f"wrote {dest / 'chunks.jsonl'}")
    print(f"wrote {dest / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
