"""Download all raw sources listed in tier_b_prose/README.md tables 2.2/2.3.

Outputs go to vault/tier_b_prose/_raw/ organized by source category.
Uses only stdlib (urllib) to avoid dependency issues outside uv.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose" / "_raw"

SOURCES: list[dict[str, str]] = [
    # 2.1 official upgrading guides (already parsed, but also keep raw rst)
    {"url": "https://raw.githubusercontent.com/godotengine/godot-docs/master/tutorials/migrating/upgrading_to_godot_4.rst", "category": "official_upgrading_guide", "slug": "upgrading_to_godot_4.rst"},
    {"url": "https://raw.githubusercontent.com/godotengine/godot-docs/master/tutorials/migrating/upgrading_to_godot_4.1.rst", "category": "official_upgrading_guide", "slug": "upgrading_to_godot_4.1.rst"},
    {"url": "https://raw.githubusercontent.com/godotengine/godot-docs/master/tutorials/migrating/upgrading_to_godot_4.2.rst", "category": "official_upgrading_guide", "slug": "upgrading_to_godot_4.2.rst"},
    {"url": "https://raw.githubusercontent.com/godotengine/godot-docs/master/tutorials/migrating/upgrading_to_godot_4.3.rst", "category": "official_upgrading_guide", "slug": "upgrading_to_godot_4.3.rst"},
    {"url": "https://raw.githubusercontent.com/godotengine/godot-docs/master/tutorials/migrating/upgrading_to_godot_4.4.rst", "category": "official_upgrading_guide", "slug": "upgrading_to_godot_4.4.rst"},
    {"url": "https://raw.githubusercontent.com/godotengine/godot-docs/master/tutorials/migrating/upgrading_to_godot_4.5.rst", "category": "official_upgrading_guide", "slug": "upgrading_to_godot_4.5.rst"},
    {"url": "https://raw.githubusercontent.com/godotengine/godot-docs/master/tutorials/migrating/upgrading_to_godot_4.6.rst", "category": "official_upgrading_guide", "slug": "upgrading_to_godot_4.6.rst"},
    {"url": "https://raw.githubusercontent.com/godotengine/godot-docs/master/tutorials/migrating/upgrading_to_godot_4.7.rst", "category": "official_upgrading_guide", "slug": "upgrading_to_godot_4.7.rst"},
    # 2.3 GDScript language docs
    {"url": "https://raw.githubusercontent.com/godotengine/godot-docs/master/tutorials/scripting/gdscript/gdscript_basics.rst", "category": "official_gdscript_doc", "slug": "gdscript_basics.rst"},
    {"url": "https://raw.githubusercontent.com/godotengine/godot-docs/master/tutorials/scripting/gdscript/gdscript_styleguide.rst", "category": "official_gdscript_doc", "slug": "gdscript_styleguide.rst"},
    {"url": "https://raw.githubusercontent.com/godotengine/godot-docs/master/getting_started/step_by_step/signals.rst", "category": "official_gdscript_doc", "slug": "signals_step_by_step.rst"},
    # 2.2 official tutorials / class reference
    {"url": "https://docs.godotengine.org/en/stable/tutorials/physics/using_character_body_2d.html", "category": "official_html_doc", "slug": "using_character_body_2d.html"},
    {"url": "https://docs.godotengine.org/en/stable/classes/class_fileaccess.html", "category": "official_html_doc", "slug": "class_fileaccess.html"},
    {"url": "https://docs.godotengine.org/en/4.4/classes/class_editorplugin.html", "category": "official_html_doc", "slug": "class_editorplugin.html"},
    # 2.2 official blogs
    {"url": "https://godotengine.org/article/core-refactoring-progress-report-2/", "category": "official_blog", "slug": "core-refactoring-progress-report-2.html"},
    {"url": "https://godotengine.org/article/multiplayer-changes-godot-4-0-report-2/", "category": "official_blog", "slug": "multiplayer-changes-godot-4-0-report-2.html"},
    # 2.2 community tutorials
    {"url": "https://uhiyama-lab.com/en/notes/godot/await-coroutine-basics/", "category": "community_blog", "slug": "await-coroutine-basics.html"},
    {"url": "https://bugnet.io/blog/fix-godot-tween-not-working-godot-4", "category": "community_blog", "slug": "fix-godot-tween-not-working-godot-4.html"},
    {"url": "https://bugnet.io/blog/fix-godot-characterbody2d-move-and-slide-not-moving", "category": "community_blog", "slug": "fix-godot-characterbody2d-move-and-slide-not-moving.html"},
    {"url": "https://bugnet.io/blog/fix-nonexistent-function-connecting-signals-godot", "category": "community_blog", "slug": "fix-nonexistent-function-connecting-signals-godot.html"},
    {"url": "https://shaggydev.com/2022/09/27/godot-4-setter-getter/", "category": "community_blog", "slug": "godot-4-setter-getter.html"},
    {"url": "https://godot-mcp.abyo.net/guides/godot4-export-annotations", "category": "community_blog", "slug": "godot4-export-annotations.html"},
    {"url": "https://bugnet.io/blog/fix-godot-rpc-call-not-working-enet-multiplayer", "category": "community_blog", "slug": "fix-godot-rpc-call-not-working-enet-multiplayer.html"},
    {"url": "https://gist.github.com/WolfgangSenff/168cb0cbd486c8c9cd507f232165b976", "category": "community_gist", "slug": "wolfgangsenff_migration_notes.html"},
    # 2.2 GitHub discussions
    {"url": "https://github.com/godotengine/godot/pull/41794", "category": "github_pr", "slug": "godot_pull_41794.md"},
    {"url": "https://github.com/godotengine/godot/pull/65271", "category": "github_pr", "slug": "godot_pull_65271.md"},
    {"url": "https://github.com/godotengine/godot-docs/issues/5577", "category": "github_issue", "slug": "godot-docs_issue_5577.md"},
    {"url": "https://github.com/godotengine/godot-docs/issues/6265", "category": "github_issue", "slug": "godot-docs_issue_6265.md"},
    {"url": "https://github.com/godotengine/godot-proposals/discussions/6192", "category": "github_discussion", "slug": "godot-proposals_discussion_6192.md"},
]


def download_one(item: dict[str, str]) -> dict[str, str | int]:
    category_dir = RAW_DIR / item["category"]
    category_dir.mkdir(parents=True, exist_ok=True)
    dest = category_dir / item["slug"]

    if item["category"].startswith("github_"):
        from download_github_api import fetch_one as fetch_github

        try:
            markdown = fetch_github(
                {
                    "kind": {
                        "github_pr": "pr",
                        "github_issue": "issue",
                        "github_discussion": "discussion",
                    }[item["category"]],
                    "owner": "godotengine",
                    "repo": {
                        "github_pr": "godot",
                        "github_issue": "godot-docs",
                        "github_discussion": "godot-proposals",
                    }[item["category"]],
                    "number": item["url"].rstrip("/").rsplit("/", 1)[-1],
                    "category": item["category"],
                    "slug": item["slug"],
                    "url": item["url"],
                }
            )
            dest.write_text(markdown, encoding="utf-8")
            html_twin = dest.with_suffix(".html")
            if html_twin.is_file():
                html_twin.unlink()
            return {
                "url": item["url"],
                "category": item["category"],
                "slug": item["slug"],
                "status": 200,
                "size": dest.stat().st_size,
                "path": f"{item['category']}/{item['slug']}",
            }
        except Exception as exc:
            return {
                "url": item["url"],
                "category": item["category"],
                "slug": item["slug"],
                "status": 0,
                "error": str(exc),
            }

    try:
        req = urllib.request.Request(
            item["url"],
            headers={"User-Agent": "Mozilla/5.0 (compatible; tier-b-crawler/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            dest.write_bytes(data)
            return {
                "url": item["url"],
                "category": item["category"],
                "slug": item["slug"],
                "status": resp.getcode(),
                "size": len(data),
                "path": str(dest),
            }
    except urllib.error.HTTPError as exc:
        return {
            "url": item["url"],
            "category": item["category"],
            "slug": item["slug"],
            "status": exc.code,
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "url": item["url"],
            "category": item["category"],
            "slug": item["slug"],
            "status": 0,
            "error": str(exc),
        }


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for item in SOURCES:
        result = download_one(item)
        results.append(result)
        status = result.get("status", 0)
        size = result.get("size", 0)
        if status == 200:
            print(f"OK  {result['category']}/{result['slug']} ({size} bytes)")
        else:
            print(f"ERR {result['category']}/{result['slug']}: {result.get('error')}")
        time.sleep(0.5)

    summary_path = RAW_DIR / "download_summary.json"
    summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSummary written to {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
