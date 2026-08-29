#!/usr/bin/env bash
# A-layer compile: vault → intermediate JSONL + prose.jsonl → artifacts/rules.db
# Does not run B-layer embedding. Does not uv sync / change the Python env.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON=("$ROOT/.venv/bin/python")
else
  PYTHON=(uv run --no-sync python)
fi

echo "==> checking vault/manifest.json against extension_api headers"
"${PYTHON[@]}" - <<'PY'
import json
import sys
from pathlib import Path

root = Path(".")
manifest = json.loads((root / "vault/manifest.json").read_text(encoding="utf-8"))
old = json.loads((root / "vault/tier_a_official/extension_api_4.0.json").read_text(encoding="utf-8"))
new = json.loads((root / "vault/tier_a_official/extension_api_target.json").read_text(encoding="utf-8"))

def ver(header: dict) -> str:
    major, minor = header["version_major"], header["version_minor"]
    patch = header.get("version_patch") or 0
    return f"{major}.{minor}.{patch}" if patch else f"{major}.{minor}"

api_from = ver(old["header"])
api_to = ver(new["header"])
errors = []
if api_from != manifest["api_from"]:
    errors.append(f"api_from mismatch: header={api_from} manifest={manifest['api_from']}")
if api_to != manifest["api_to"]:
    errors.append(f"api_to mismatch: header={api_to} manifest={manifest['api_to']}")
if manifest["godot_version"] != manifest["api_to"]:
    errors.append(
        f"godot_version {manifest['godot_version']!r} != api_to {manifest['api_to']!r}"
    )
if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
print(f"  ok: godot={manifest['godot_version']} api {api_from} → {api_to} schema={manifest['schema_version']}")
PY

echo "==> parse_renames_cpp.py"
"${PYTHON[@]}" build/parse_renames_cpp.py

echo "==> diff_extension_api.py"
"${PYTHON[@]}" build/diff_extension_api.py

echo "==> parse_upgrading_docs.py"
"${PYTHON[@]}" build/parse_upgrading_docs.py

echo "==> build_tier_a.py"
"${PYTHON[@]}" build/build_tier_a.py

echo "==> A-layer build finished"
ls -lh artifacts/rules.db artifacts/manifest.lock.json artifacts/build_report.md
ls vault/tier_b_prose/*.prose.jsonl 2>/dev/null || true
