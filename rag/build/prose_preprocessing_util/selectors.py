"""Common prose selection helpers.

Each selector returns ``(keep, drop, uncertain)`` triples of the original
block objects (not copies), so ``combine_select`` can merge by identity.
Specification: rag/vault/tier_b_prose/CHUNKING.md §4.3
"""

from __future__ import annotations

from typing import Any, Iterable

from .ir import ProseBlock


def _haystack(block: ProseBlock) -> str:
    return " ".join(block.heading_path) + "\n" + block.text


def _substring_hit(haystack: str, needles: Iterable[str]) -> bool:
    lowered = haystack.lower()
    for needle in needles:
        n = needle.strip()
        if n and n.lower() in lowered:
            return True
    return False


def heading_allowlist_select(
    blocks: list[ProseBlock], allowlist: list[str]
) -> tuple[list[ProseBlock], list[ProseBlock], list[ProseBlock]]:
    """Keep blocks whose heading_path hits allowlist substrings.

    If the allowlist is empty, every block is marked uncertain so callers
    can decide whether to keep or drop downstream.
    """
    if not allowlist:
        return [], [], list(blocks)
    keep: list[ProseBlock] = []
    uncertain: list[ProseBlock] = []
    for block in blocks:
        path = " ".join(block.heading_path)
        if block.type == "heading":
            path = path + " " + block.text
        if _substring_hit(path, allowlist):
            keep.append(block)
        else:
            uncertain.append(block)
    return keep, [], uncertain


def heading_denylist_select(
    blocks: list[ProseBlock], denylist: list[str]
) -> tuple[list[ProseBlock], list[ProseBlock], list[ProseBlock]]:
    """Drop blocks whose heading_path (or heading text) hits denylist substrings."""
    drop: list[ProseBlock] = []
    uncertain: list[ProseBlock] = []
    for block in blocks:
        path = " ".join(block.heading_path)
        if block.type == "heading":
            path = path + " " + block.text
        if _substring_hit(path, denylist):
            drop.append(block)
        else:
            uncertain.append(block)
    return [], drop, uncertain


def keyword_allowlist_select(
    blocks: list[ProseBlock], keywords: list[str]
) -> tuple[list[ProseBlock], list[ProseBlock], list[ProseBlock]]:
    """Keep blocks whose text or heading_path hits migration-related keywords.

    An empty keyword list leaves every block uncertain so callers can keep
    all blocks while still using the keywords separately for tagging.
    """
    if not keywords:
        return [], [], list(blocks)
    keep: list[ProseBlock] = []
    uncertain: list[ProseBlock] = []
    for block in blocks:
        if _substring_hit(_haystack(block), keywords):
            keep.append(block)
        else:
            uncertain.append(block)
    return keep, [], uncertain


def topic_map_select(
    blocks: list[ProseBlock], topic_map: dict[str, Any]
) -> tuple[list[ProseBlock], list[ProseBlock], list[ProseBlock]]:
    """Keep blocks matching topic_map entries (OS / RPC / Tween, etc.).

    Accepts either ``{"topics": ["OS", ...]}`` (the vault YAML shape) or a
    mapping of topic → extra keywords. An empty topic list leaves every block
    uncertain so callers can keep all blocks.
    """
    topics: list[str] = []
    if "topics" in topic_map and isinstance(topic_map["topics"], list):
        topics.extend(str(t) for t in topic_map["topics"])
    else:
        topics.extend(str(k) for k in topic_map.keys())
        for value in topic_map.values():
            if isinstance(value, list):
                topics.extend(str(v) for v in value)
            elif isinstance(value, str):
                topics.append(value)
    if not topics:
        return [], [], list(blocks)
    keep: list[ProseBlock] = []
    uncertain: list[ProseBlock] = []
    for block in blocks:
        if _substring_hit(_haystack(block), topics):
            keep.append(block)
        else:
            uncertain.append(block)
    return keep, [], uncertain


def maintainer_select(
    blocks: list[ProseBlock], logins: list[str]
) -> tuple[list[ProseBlock], list[ProseBlock], list[ProseBlock]]:
    """Keep blocks authored by maintainer logins.

    Login is matched against ``subtype``, ``heading_path``, and the block text
    (parsers stash the GitHub login in ``subtype`` and/or a heading).

    An empty login list leaves every block uncertain; callers can then route
    all blocks to human review instead of auto-dropping non-maintainer content.
    """
    lowered = {login.lower() for login in logins if login}
    if not lowered:
        return [], [], list(blocks)
    keep: list[ProseBlock] = []
    uncertain: list[ProseBlock] = []
    for block in blocks:
        parts = [block.subtype or "", *block.heading_path, block.text[:200]]
        blob = " ".join(parts).lower()
        if any(login in blob for login in lowered):
            keep.append(block)
        else:
            uncertain.append(block)
    return keep, [], uncertain


def combine_select(
    *results: tuple[list[ProseBlock], list[ProseBlock], list[ProseBlock]],
) -> tuple[list[ProseBlock], list[ProseBlock], list[ProseBlock]]:
    """Merge selector triples: denylist (drop) wins, then allowlist (keep)."""
    by_id: dict[str, ProseBlock] = {}
    drop_ids: set[str] = set()
    keep_ids: set[str] = set()
    for keep, drop, uncertain in results:
        for block in (*keep, *drop, *uncertain):
            by_id[block.block_id] = block
        drop_ids.update(b.block_id for b in drop)
        keep_ids.update(b.block_id for b in keep)
    keep_ids -= drop_ids

    keep: list[ProseBlock] = []
    drop: list[ProseBlock] = []
    uncertain: list[ProseBlock] = []
    # Preserve first-seen order.
    for block_id, block in by_id.items():
        if block_id in drop_ids:
            drop.append(block)
        elif block_id in keep_ids:
            keep.append(block)
        else:
            uncertain.append(block)
    return keep, drop, uncertain
