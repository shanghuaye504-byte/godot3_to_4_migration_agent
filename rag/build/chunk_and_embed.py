"""兼容旧命令的薄封装：先 ``chunk_prose``，再 ``embed_prose``。

对比不同切块策略时请直接调两个脚本，不要走本封装::

    cd rag
    uv run python build/chunk_prose.py --strategy-id default
    uv run python build/embed_prose.py --strategy-id default

切块 CLI 参数（``--mode`` / ``--overlap`` / ``--max-tokens`` 等）原样转给
``chunk_prose.py``。embed 阶段只转发 ``--strategy-id``。

跳过 embedding（不拉 Hugging Face、不写 LanceDB）::

    uv run python build/chunk_and_embed.py --skip-embed
    TIER_B_SKIP_EMBED=1 uv run python build/chunk_and_embed.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BUILD_DIR = Path(__file__).resolve().parent
if str(_BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(_BUILD_DIR))
_WORKSPACE = _BUILD_DIR.parent.parent
if str(_WORKSPACE) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE))

from prose_preprocessing_util.chunker import DEFAULT_STRATEGY_ID  # noqa: E402

import chunk_prose  # noqa: E402
import embed_prose  # noqa: E402


def _strategy_id(argv: list[str]) -> str:
    if "--strategy-id" in argv:
        idx = argv.index("--strategy-id")
        if idx + 1 < len(argv):
            return argv[idx + 1]
    return DEFAULT_STRATEGY_ID


def main() -> int:
    skip = (
        "--skip-embed" in sys.argv
        or os.environ.get("TIER_B_SKIP_EMBED", "").strip().lower() in {"1", "true", "yes"}
    )
    extra = [a for a in sys.argv[1:] if a != "--skip-embed"]
    rc = chunk_prose.main(extra)
    if rc != 0:
        return rc
    if skip:
        print("skip embed (TIER_B_SKIP_EMBED / --skip-embed)")
        return 0
    return embed_prose.main(["--strategy-id", _strategy_id(extra)])


if __name__ == "__main__":
    raise SystemExit(main())
