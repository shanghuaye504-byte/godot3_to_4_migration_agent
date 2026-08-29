"""Merge intermediate JSONL + YAML → ``artifacts/rules.db``.

The only program that writes the SQLite database. Adapters must not touch it.
YAML is insert-only (no overlay). ``not_actively_handled`` and
``preflight_probe_recommended`` are read then dropped (archive-only).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BUILD_DIR = Path(__file__).resolve().parent
if str(_BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(_BUILD_DIR))

from _util import (  # noqa: E402
    ARTIFACTS,
    INTERMEDIATE,
    MANUAL,
    RAG_ROOT,
    VAULT,
    load_manifest,
    write_jsonl,
    write_report_json,
)
from rag.retriever.schemas import (  # noqa: E402
    SKIP_DETECTION_METHODS,
    AgentAction,
    ChangeKind,
    DetectionMethod,
    MigrationRule,
    SymbolKind,
)
from rag.version_codec import version_to_code  # noqa: E402

DDL = """
CREATE TABLE migration_rules (
  id                   TEXT PRIMARY KEY,
  old_symbol           TEXT,
  new_symbol           TEXT,
  owner                TEXT,
  symbol_kind          TEXT NOT NULL,
  change               TEXT NOT NULL,
  rule_kind            TEXT,
  match_tokens         TEXT NOT NULL DEFAULT '[]',
  trigger              TEXT,
  since_version        TEXT,
  since_version_code   INTEGER NOT NULL DEFAULT 0,
  until_version        TEXT,
  until_version_code   INTEGER,
  detection_method     TEXT NOT NULL DEFAULT 'agent_retrieval',
  semantic_risk        INTEGER NOT NULL DEFAULT 0,
  converter_gap        INTEGER NOT NULL DEFAULT 0,
  verifier_blind       INTEGER NOT NULL DEFAULT 0,
  agent_action         TEXT,
  system_action        TEXT,
  warning              TEXT,
  snippet              TEXT,
  source               TEXT NOT NULL,
  source_url           TEXT,
  confidence           TEXT,
  payload              TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_mr_old         ON migration_rules(old_symbol);
CREATE INDEX idx_mr_new         ON migration_rules(new_symbol);
CREATE INDEX idx_mr_owner       ON migration_rules(owner);
CREATE INDEX idx_mr_detect      ON migration_rules(detection_method);
CREATE INDEX idx_mr_since_code  ON migration_rules(since_version_code);
CREATE INDEX idx_mr_old_since   ON migration_rules(old_symbol, since_version_code);

CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

JSONL_FILES = (
    "renames.jsonl",
    "api_diff.jsonl",
    "rst_4x.jsonl",
    "manual.jsonl",
)

SCANNER_METHODS = {
    DetectionMethod.static_scan_post_l0,
    DetectionMethod.verify_error_filter,
}
AGENT_METHODS = {
    DetectionMethod.agent_retrieval,
    DetectionMethod.agent_retrieval_or_escalate,
}


def _flatten_action(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return " ".join(value.split())
    return str(value)


def yaml_entry_to_rule(entry: dict[str, Any], *, default_source: str) -> MigrationRule | None:
    raw_dm = entry["detection_method"]
    dm = DetectionMethod(raw_dm)
    if dm in SKIP_DETECTION_METHODS:
        return None

    trigger = entry.get("trigger") or {}
    symbol = trigger.get("symbol") if isinstance(trigger, dict) else None
    explicit_tokens = entry.get("match_tokens")
    tokens: list[str] = list(explicit_tokens) if explicit_tokens else []
    if symbol and symbol not in tokens:
        tokens.insert(0, symbol)

    action_text = _flatten_action(entry.get("action"))
    source = entry.get("source") or default_source

    if "symbol_kind" in entry:
        symbol_kind = SymbolKind(entry["symbol_kind"])
    elif default_source == "manual_rewrite":
        symbol_kind = SymbolKind.rewrite
    elif default_source == "official_prose_3to4_shader":
        symbol_kind = SymbolKind.shader
    else:
        symbol_kind = SymbolKind.trap

    if "change" in entry:
        change = ChangeKind(entry["change"])
    elif default_source == "manual_rewrite":
        change = ChangeKind.rewrite
    elif entry.get("kind") == "guard_false_positive":
        change = ChangeKind.false_positive
    else:
        change = ChangeKind.trap

    system_action = None
    agent_action = None
    warning = None
    if "agent_action" in entry and entry["agent_action"]:
        agent_action = AgentAction(entry["agent_action"])
        warning = action_text
    elif dm in SCANNER_METHODS:
        system_action = action_text
        agent_action = None
    elif dm == DetectionMethod.agent_retrieval_or_escalate:
        agent_action = AgentAction.escalate_human
        warning = action_text
    elif dm in AGENT_METHODS:
        agent_action = AgentAction.apply_and_warn
        warning = action_text

    since = entry.get("since_version")
    if since is None or since == "null":
        since = None
    elif isinstance(since, float):
        # YAML 1.1 parses 4.0 / 4.4 as floats.
        since = str(since)
    elif isinstance(since, int):
        since = f"{since}.0"
    else:
        since = str(since)

    kind = entry.get("kind")
    converter_gap = bool(entry.get("converter_gap")) or kind == "converter_gap"
    verifier_blind = bool(entry.get("verifier_blind"))
    if dm == DetectionMethod.static_scan_post_l0 and "verifier_blind" not in entry:
        verifier_blind = True

    notes = entry.get("notes")
    snippet = notes.strip() if isinstance(notes, str) and notes.strip() else None

    owner = symbol if symbol_kind in {SymbolKind.trap, SymbolKind.class_} else None
    if default_source == "manual_trap" and symbol:
        owner = symbol

    return MigrationRule(
        id=entry["id"],
        old_symbol=symbol,
        new_symbol=entry.get("new_symbol"),
        owner=owner,
        symbol_kind=symbol_kind,
        change=change,
        rule_kind=kind,
        match_tokens=tokens,
        trigger=trigger if trigger else None,
        since_version=since,
        since_version_code=version_to_code(since),
        detection_method=dm,
        semantic_risk=bool(entry.get("semantic_risk")),
        converter_gap=converter_gap,
        verifier_blind=verifier_blind,
        agent_action=agent_action,
        system_action=system_action,
        warning=warning,
        snippet=snippet,
        source=source,
        source_url=entry.get("source_url"),
        confidence=entry.get("confidence"),
        payload={},
    )


def load_manual_yaml() -> tuple[list[MigrationRule], int]:
    import yaml

    rules: list[MigrationRule] = []
    skipped = 0

    traps_path = MANUAL / "semantic_rewrites.yaml"
    data = yaml.safe_load(traps_path.read_text(encoding="utf-8")) or {}
    for entry in data.get("known_traps") or []:
        rule = yaml_entry_to_rule(entry, default_source="manual_trap")
        if rule is None:
            skipped += 1
            print(f"  skip archive trap {entry.get('id')} ({entry.get('detection_method')})")
            continue
        rules.append(rule)
    for entry in data.get("semantic_rewrites") or []:
        rule = yaml_entry_to_rule(entry, default_source="manual_rewrite")
        if rule is None:
            skipped += 1
            continue
        rules.append(rule)

    shader_path = MANUAL / "shader_3to4_carveout.yaml"
    shader = yaml.safe_load(shader_path.read_text(encoding="utf-8")) or {}
    for entry in shader.get("shader_carveouts") or []:
        rule = yaml_entry_to_rule(entry, default_source="official_prose_3to4_shader")
        if rule is None:
            skipped += 1
            continue
        rules.append(rule)

    return rules, skipped


def load_jsonl(path: Path) -> list[MigrationRule]:
    rows: list[MigrationRule] = []
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(MigrationRule.model_validate_json(line))
            except Exception as exc:
                raise RuntimeError(f"{path.name}:{line_no}: {exc}") from exc
    return rows


def rule_to_sql_params(rule: MigrationRule) -> dict[str, Any]:
    d = rule.model_dump(mode="json")
    d["match_tokens"] = json.dumps(d["match_tokens"], ensure_ascii=False)
    d["trigger"] = json.dumps(d["trigger"], ensure_ascii=False) if d.get("trigger") is not None else None
    d["payload"] = json.dumps(d.get("payload") or {}, ensure_ascii=False)
    d["semantic_risk"] = int(d["semantic_risk"])
    d["converter_gap"] = int(d["converter_gap"])
    d["verifier_blind"] = int(d["verifier_blind"])
    return d


INSERT_SQL = """
INSERT INTO migration_rules (
  id, old_symbol, new_symbol, owner, symbol_kind, change, rule_kind,
  match_tokens, trigger, since_version, since_version_code,
  until_version, until_version_code, detection_method,
  semantic_risk, converter_gap, verifier_blind,
  agent_action, system_action, warning, snippet,
  source, source_url, confidence, payload
) VALUES (
  :id, :old_symbol, :new_symbol, :owner, :symbol_kind, :change, :rule_kind,
  :match_tokens, :trigger, :since_version, :since_version_code,
  :until_version, :until_version_code, :detection_method,
  :semantic_risk, :converter_gap, :verifier_blind,
  :agent_action, :system_action, :warning, :snippet,
  :source, :source_url, :confidence, :payload
)
"""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_vault() -> dict[str, Any]:
    files: dict[str, Any] = {}
    for path in sorted(VAULT.rglob("*")):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        rel = path.relative_to(RAG_ROOT).as_posix()
        files[rel] = {"sha256": _sha256(path), "bytes": path.stat().st_size}
    return files


def _load_adapter_reports() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for path in sorted(INTERMEDIATE.glob("_report_*.json")):
        out[path.stem.removeprefix("_report_")] = json.loads(path.read_text(encoding="utf-8"))
    return out


def write_build_report(
    *,
    n_written: int,
    collisions: list[dict[str, str]],
    skipped_yaml: int,
    by_source: Counter,
    by_detect: Counter,
    by_kind: Counter,
    adapter_reports: dict[str, Any],
) -> None:
    prose_files = sorted(p.name for p in (VAULT / "tier_b_prose").glob("*.prose.jsonl"))
    unclassified = (adapter_reports.get("rst") or {}).get("unclassified") or []
    lines = [
        "# A-layer build report",
        "",
        f"Built at: {datetime.now(timezone.utc).isoformat()}",
        f"Total rows in rules.db: **{n_written}**",
        f"YAML archive entries skipped (not inserted): **{skipped_yaml}**",
        f"ID collisions (later source won): **{len(collisions)}**",
        "",
        "## By source",
        "",
        "| source | rows |",
        "| --- | ---: |",
    ]
    for k, v in sorted(by_source.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| `{k}` | {v} |")
    lines += [
        "",
        "## By detection_method",
        "",
        "| detection_method | rows |",
        "| --- | ---: |",
    ]
    for k, v in sorted(by_detect.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| `{k}` | {v} |")
    lines += [
        "",
        "## By symbol_kind (top)",
        "",
        "| symbol_kind | rows |",
        "| --- | ---: |",
    ]
    for k, v in by_kind.most_common(20):
        lines.append(f"| `{k}` | {v} |")

    cpp = adapter_reports.get("renames") or {}
    lines += [
        "",
        "## Adapter notes",
        "",
        f"- cpp unrecognized lines: **{cpp.get('unrecognized_count', 'n/a')}**",
        f"- rst unclassified (kept as `behavior`/`needs_review`): **{len(unclassified)}**",
        "",
        "## Prose intermediate files (`vault/tier_b_prose/`)",
        "",
    ]
    for name in prose_files:
        lines.append(f"- `{name}`")
    if unclassified:
        lines += ["", "## Unclassified rst rows (first 30)", ""]
        for item in unclassified[:30]:
            snippet = (item.get("snippet") or "").replace("\n", " ")
            if len(snippet) > 160:
                snippet = snippet[:157] + "..."
            lines.append(
                f"- `{item.get('file')}` / `{item.get('owner')}`: {snippet}"
            )
    if collisions:
        lines += ["", "## ID collisions", ""]
        for c in collisions[:40]:
            lines.append(
                f"- `{c['id']}` first=`{c['first_source']}` later=`{c['later_source']}`"
            )
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "build_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    manifest = load_manifest()
    print("build_tier_a: loading YAML …")
    manual_rules, skipped_yaml = load_manual_yaml()
    write_jsonl(INTERMEDIATE / "manual.jsonl", manual_rules)
    print(f"  manual insert rows={len(manual_rules)} skipped_archive={skipped_yaml}")

    merged: dict[str, MigrationRule] = {}
    collisions: list[dict[str, str]] = []
    order_sources = []
    for name in JSONL_FILES:
        path = INTERMEDIATE / name
        if not path.exists():
            raise FileNotFoundError(f"missing {path}; run adapters first")
        rows = load_jsonl(path)
        order_sources.append((name, len(rows)))
        print(f"  {name}: {len(rows)}")
        for rule in rows:
            MigrationRule.model_validate(rule.model_dump())
            if rule.id in merged:
                collisions.append(
                    {
                        "id": rule.id,
                        "first_source": merged[rule.id].source,
                        "later_source": rule.source,
                    }
                )
            merged[rule.id] = rule

    db_path = ARTIFACTS / "rules.db"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.executescript(DDL)
    for rule in merged.values():
        conn.execute(INSERT_SQL, rule_to_sql_params(rule))

    built_at = datetime.now(timezone.utc).isoformat()
    meta = {
        "schema_version": str(manifest.get("schema_version") or "2"),
        "godot_version": manifest["godot_version"],
        "docs_checkout": manifest["docs_checkout"],
        "api_from": manifest["api_from"],
        "api_to": manifest["api_to"],
        "built_at": built_at,
    }
    for k, v in meta.items():
        conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()

    lock = {
        "built_at": built_at,
        "schema_version": meta["schema_version"],
        "manifest": manifest,
        "files": _hash_vault(),
        "row_count": len(merged),
    }
    (ARTIFACTS / "manifest.lock.json").write_text(
        json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    by_source: Counter = Counter(r.source for r in merged.values())
    by_detect: Counter = Counter(r.detection_method.value for r in merged.values())
    by_kind: Counter = Counter(r.symbol_kind.value for r in merged.values())
    adapter_reports = _load_adapter_reports()
    write_build_report(
        n_written=len(merged),
        collisions=collisions,
        skipped_yaml=skipped_yaml,
        by_source=by_source,
        by_detect=by_detect,
        by_kind=by_kind,
        adapter_reports=adapter_reports,
    )
    write_report_json(
        "tier_a",
        {
            "row_count": len(merged),
            "skipped_yaml": skipped_yaml,
            "collisions": collisions,
            "by_source": dict(by_source),
            "jsonl": dict(order_sources),
        },
    )
    print(f"build_tier_a: wrote {len(merged)} rows → {db_path}")
    print(f"  collisions={len(collisions)} yaml_skipped={skipped_yaml}")
    print(f"  by source: {dict(by_source)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
