"""Next-stage B-layer script (write LanceDB from embedded chunks).

This round only compiles A-layer (``rules.db`` + ``*.prose.jsonl``).
"""

from __future__ import annotations

import sys

if __name__ == "__main__":
    sys.exit(
        "build_tier_b.py is the next-stage B-layer compiler and is not run "
        "in this round. It would write artifacts/corpus.lance; this round "
        "stops at vault/tier_b_prose intermediate JSONL."
    )
