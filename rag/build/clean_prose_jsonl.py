"""Clean docutils system_message noise from existing tier_b_prose jsonl files.

When :ref: roles fail to resolve, docutils embeds error text into paragraph
astext() output. This script removes those noise lines from existing prose
jsonl records and rewrites the files in place.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROSE_DIR = Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose"

# Patterns that identify docutils system_message text leaking into astext().
NOISE_PATTERNS = [
    re.compile(r".*:\s*\(INFO/\d+\) No role entry for"),
    re.compile(r".*:\s*\(ERROR/\d+\) Unknown interpreted text role"),
    re.compile(r'Trying "[^"]+" as canonical role name\.'),
]


def is_noise_line(line: str) -> bool:
    return any(p.match(line) for p in NOISE_PATTERNS)


def clean_text(text: str) -> str:
    lines = text.splitlines()
    cleaned = [line for line in lines if not is_noise_line(line)]
    return "\n".join(cleaned).strip()


def clean_file(path: Path) -> tuple[int, int]:
    """Return (records_read, records_changed)."""
    records: list[dict] = []
    changed = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        rec = json.loads(raw)
        original = rec.get("text", "")
        cleaned = clean_text(original)
        if cleaned != original:
            rec["text"] = cleaned
            changed += 1
        records.append(rec)

    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return len(records), changed


def main() -> int:
    if not PROSE_DIR.exists():
        print(f"Prose directory not found: {PROSE_DIR}", file=sys.stderr)
        return 1

    total_records = 0
    total_changed = 0
    for path in sorted(PROSE_DIR.glob("*.prose.jsonl")):
        records, changed = clean_file(path)
        total_records += records
        total_changed += changed
        print(f"  {path.name}: {records} records, {changed} cleaned")

    print(f"Total: {total_records} records, {total_changed} cleaned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
