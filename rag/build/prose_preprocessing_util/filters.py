"""Common prose content filters.

Usage: process_<bucket>.py scripts import and compose these functions.
Specification: rag/vault/tier_b_prose/CHUNKING.md §4.2

Not every bucket uses every filter. Type A (official upgrading-guide
``*.prose.jsonl``) is lifted by the chunker and never goes through these.
Type B uses length 40; C/D/F/G use 80; E uses 20. Type C additionally uses
``signature_density_filter``; type E uses ``github_noise_filter``.
"""

from __future__ import annotations

import re
from pathlib import Path

from .ir import ProseBlock

# Keep code and headings even when they are shorter than min_chars: a one-line
# ``@export var speed := 0`` example is still a retrieval unit, and headings
# exist so heading_path is reconstructable (the chunker skips type=heading).
_SKIP_LENGTH_TYPES = frozenset({"heading", "code"})

_SIGNATURE_TOKEN_RE = re.compile(
    r"\b(?:void|static|const|var|func|bool|int|float|String|Array|"
    r"Dictionary|Packed\w+|Variant|RID|Callable|Signal|NodePath|"
    r"Vector[23]|Color|Transform\w*|AABB|Plane|Quat|Basis)\b"
    r"|[A-Z][A-Za-z0-9]+(?:2D|3D)?"
    r"|\(\)"
    r"|:\s*[A-Z]",
)

_GITHUB_NOISE_RE = re.compile(
    r"^\s*(?:"
    r"\+1|:-?1:|👍|👎|❤️|🎉|🚀|👀"
    r"|thanks(?: you)?[!.,]?"
    r"|thank you[!.,]?"
    r"|any update\??"
    r"|bump[!.,]?"
    r"|this[!.,]?"
    r"|same[!.,]?"
    r"|subscribed"
    r"|fyi"
    r")\s*$",
    re.IGNORECASE,
)

_EMOJI_ONLY_RE = re.compile(
    r"^[\s"
    r"\U0001F300-\U0001FAFF"
    r"\u2600-\u27BF"
    r":+\-_.!?]+$",
)

# High-confidence noise patterns applied by ``noise_filter`` to every bucket.
_MARKDOWN_IMAGE_RE = re.compile(r"^!\[.*?\]\(.*?\)$")
_MARKDOWN_LINK_RE = re.compile(r"^\[.*?\]\(.*?\)$")
_BARE_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_GITHUB_SYNTHETIC_HEADING_RE = re.compile(r"^(?:body|comment) by \w+", re.IGNORECASE)
_LOCAL_PATH_RE = re.compile(r"/Users/|/home/|/var/|/tmp/|/private/")
_DOCUTILS_WARNING_RE = re.compile(r"\((?:INFO|WARNING|ERROR)/1\)")


def load_boilerplate_patterns(path: Path) -> list[re.Pattern[str]]:
    """Load one regex per non-comment line from ``boilerplate_patterns.txt``."""
    patterns: list[re.Pattern[str]] = []
    if not path.exists():
        return patterns
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(re.compile(line, re.IGNORECASE))
    return patterns


def length_filter(blocks: list[ProseBlock], min_chars: int) -> list[ProseBlock]:
    """Drop non-code, non-heading blocks whose stripped text is too short."""
    kept: list[ProseBlock] = []
    for block in blocks:
        if block.type in _SKIP_LENGTH_TYPES:
            kept.append(block)
            continue
        if len(block.text.strip()) >= min_chars:
            kept.append(block)
    return kept


def boilerplate_filter(
    blocks: list[ProseBlock], patterns: list[re.Pattern[str]]
) -> list[ProseBlock]:
    """Drop blocks whose text matches any boilerplate regex."""
    if not patterns:
        return list(blocks)
    kept: list[ProseBlock] = []
    for block in blocks:
        text = block.text
        if any(p.search(text) for p in patterns):
            continue
        kept.append(block)
    return kept


def signature_density_filter(
    blocks: list[ProseBlock], threshold: float = 0.5
) -> list[ProseBlock]:
    """Drop blocks where type-signature-like tokens dominate.

    Used by type C (Sphinx class pages) to throw away API signature tables
    that A-layer ``extension_api.json`` already covers.
    """
    kept: list[ProseBlock] = []
    for block in blocks:
        if block.type in {"code", "heading"}:
            kept.append(block)
            continue
        heading = " ".join(block.heading_path).lower()
        if any(
            marker in heading
            for marker in ("properties", "methods", "enumerations", "signals", "constants")
        ) and block.type in {"list", "paragraph"}:
            # Class-ref tables live under these headings; drop the rows even
            # when density is just under the threshold.
            if _signature_density(block.text) >= min(threshold, 0.35):
                continue
        density = _signature_density(block.text)
        if density >= threshold:
            continue
        kept.append(block)
    return kept


def _signature_density(text: str) -> float:
    tokens = re.findall(r"\S+", text)
    if not tokens:
        return 0.0
    hits = 0
    for tok in tokens:
        if _SIGNATURE_TOKEN_RE.search(tok) or "(" in tok:
            hits += 1
    return hits / len(tokens)


def github_noise_filter(blocks: list[ProseBlock]) -> list[ProseBlock]:
    """Drop +1 / Thanks / Any update? / emoji-only comments (type E)."""
    kept: list[ProseBlock] = []
    for block in blocks:
        if block.type in {"code", "heading"}:
            kept.append(block)
            continue
        stripped = block.text.strip()
        if not stripped:
            continue
        if _GITHUB_NOISE_RE.match(stripped):
            continue
        if len(stripped) <= 12 and _EMOJI_ONLY_RE.match(stripped):
            continue
        kept.append(block)
    return kept


def noise_filter(blocks: list[ProseBlock]) -> list[ProseBlock]:
    """Drop high-confidence noise common to all buckets.

    This is a conservative denylist: only remove things that are almost
    certainly not migration knowledge (synthetic headings, bare links/images,
    local filesystem paths, docutils build warnings, and extremely short
    non-structural blocks).
    """
    kept: list[ProseBlock] = []
    for block in blocks:
        text = block.text.strip()
        if not text:
            continue

        # Synthetic GitHub headings like "body by KoBeWi" / "comment by Xrayez".
        if block.type == "heading" and _GITHUB_SYNTHETIC_HEADING_RE.match(text):
            continue

        # Pure markdown images, links, or bare URLs carry no prose signal.
        if _MARKDOWN_IMAGE_RE.match(text) or _BARE_URL_RE.match(text):
            continue

        # Treat a single markdown link as noise, but keep paragraphs that
        # contain a link among real text.
        if _MARKDOWN_LINK_RE.match(text):
            continue

        # Docutils build warnings and leaked local paths.
        if _DOCUTILS_WARNING_RE.search(text) or _LOCAL_PATH_RE.search(text):
            continue

        # Drop very short non-structural blocks (headings and code are kept
        # because they carry structure or examples even when brief).
        if block.type not in {"heading", "code"} and len(text.split()) < 3:
            continue

        kept.append(block)
    return kept
