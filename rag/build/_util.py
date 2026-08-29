"""Shared paths and JSONL helpers for A-layer adapters. Not a public API."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable

RAG_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = RAG_ROOT.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from rag.retriever.schemas import MigrationRule  # noqa: E402

VAULT = RAG_ROOT / "vault"
OFFICIAL = VAULT / "tier_a_official"
MANUAL = VAULT / "tier_a_manual"
PROSE_DIR = VAULT / "tier_b_prose"
INTERMEDIATE = RAG_ROOT / "build" / "intermediate"
ARTIFACTS = RAG_ROOT / "artifacts"
MANIFEST_PATH = VAULT / "manifest.json"


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def make_id(
    source: str,
    since: str | None,
    owner: str | None,
    symbol_kind: str,
    symbol: str | None,
    extra: str | None = None,
) -> str:
    parts = [source, since or "0", owner or "_", symbol_kind, symbol or "_"]
    if extra:
        parts.append(extra)
    return ":".join(parts)


def write_jsonl(path: Path, rules: Iterable[MigrationRule]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for rule in rules:
            validated = (
                rule if isinstance(rule, MigrationRule) else MigrationRule.model_validate(rule)
            )
            MigrationRule.model_validate(validated.model_dump())
            fh.write(validated.model_dump_json() + "\n")
            n += 1
    return n


def write_report_json(name: str, payload: dict[str, Any]) -> None:
    INTERMEDIATE.mkdir(parents=True, exist_ok=True)
    (INTERMEDIATE / f"_report_{name}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def header_version_string(api: dict[str, Any]) -> str:
    h = api["header"]
    major = h["version_major"]
    minor = h["version_minor"]
    patch = h.get("version_patch") or 0
    if patch:
        return f"{major}.{minor}.{patch}"
    return f"{major}.{minor}"
