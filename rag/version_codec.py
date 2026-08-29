"""Single version↔int codec shared by build (write) and retriever (read).

Must stay byte-identical on both sides: SQL filters with
``since_version_code <= target_version_code``. Do not reimplement this in
``build/`` or ``retriever/``.
"""

from __future__ import annotations


def version_to_code(v: str | None) -> int:
    """Encode ``'4.0'`` → 40000, ``'4.7.1'`` → 40701, ``None``/empty → 0.

    Formula: ``major * 10000 + minor * 100 + patch``.
    """
    if not v:
        return 0
    major, minor, *rest = (int(x) for x in v.split("."))
    patch = rest[0] if rest else 0
    return major * 10000 + minor * 100 + patch
