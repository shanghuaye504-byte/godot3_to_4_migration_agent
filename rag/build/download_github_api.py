"""Download type-E GitHub sources as Markdown via the GitHub API.

Replaces noisy HTML snapshots under vault/tier_b_prose/_raw/github_*.
Uses the ``gh`` CLI so auth goes through ``gh auth login`` (no token in code).

Run from rag/:
    .venv/bin/python build/download_github_api.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

RAW_DIR = Path(__file__).resolve().parent.parent / "vault" / "tier_b_prose" / "_raw"

GITHUB_SOURCES: list[dict[str, str]] = [
    {
        "kind": "pr",
        "owner": "godotengine",
        "repo": "godot",
        "number": "41794",
        "category": "github_pr",
        "slug": "godot_pull_41794.md",
        "url": "https://github.com/godotengine/godot/pull/41794",
    },
    {
        "kind": "pr",
        "owner": "godotengine",
        "repo": "godot",
        "number": "65271",
        "category": "github_pr",
        "slug": "godot_pull_65271.md",
        "url": "https://github.com/godotengine/godot/pull/65271",
    },
    {
        "kind": "issue",
        "owner": "godotengine",
        "repo": "godot-docs",
        "number": "5577",
        "category": "github_issue",
        "slug": "godot-docs_issue_5577.md",
        "url": "https://github.com/godotengine/godot-docs/issues/5577",
    },
    {
        "kind": "issue",
        "owner": "godotengine",
        "repo": "godot-docs",
        "number": "6265",
        "category": "github_issue",
        "slug": "godot-docs_issue_6265.md",
        "url": "https://github.com/godotengine/godot-docs/issues/6265",
    },
    {
        "kind": "discussion",
        "owner": "godotengine",
        "repo": "godot-proposals",
        "number": "6192",
        "category": "github_discussion",
        "slug": "godot-proposals_discussion_6192.md",
        "url": "https://github.com/godotengine/godot-proposals/discussions/6192",
    },
]

_DISCUSSION_QUERY = """
query ($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    discussion(number: $number) {
      body
      author { login }
      comments(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { body author { login } }
      }
    }
  }
}
"""


def _gh_api(path: str) -> Any:
    """GET a REST path via ``gh api``. Raises on non-zero exit."""
    result = subprocess.run(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"gh api {path} failed: {err[:500]}")
    return json.loads(result.stdout)


def _gh_api_list(path: str) -> list[dict]:
    """Paginate a REST list endpoint (100 items per page)."""
    items: list[dict] = []
    page = 1
    while True:
        sep = "&" if "?" in path else "?"
        chunk = _gh_api(f"{path}{sep}per_page=100&page={page}")
        if not isinstance(chunk, list) or not chunk:
            break
        items.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    return items


def _gh_graphql(variables: dict[str, Any]) -> dict:
    payload = json.dumps({"query": _DISCUSSION_QUERY, "variables": variables})
    result = subprocess.run(
        ["gh", "api", "graphql", "--input", "-"],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"gh api graphql failed: {err[:500]}")
    body = json.loads(result.stdout)
    if body.get("errors"):
        raise RuntimeError(f"graphql errors: {body['errors']}")
    return body


def compose_markdown(root: dict, comments: list, extra: list) -> str:
    """Stable heading format consumed by parse_markdown + maintainer_select."""
    login = ((root.get("user") or {}).get("login")) or "op"
    parts = [f"# body by {login}", root.get("body") or ""]
    for comment in list(comments or []) + list(extra or []):
        clogin = ((comment.get("user") or {}).get("login")) or "unknown"
        parts.append(f"## comment by {clogin}")
        parts.append(comment.get("body") or "")
    return "\n\n".join(parts)


def fetch_discussion_markdown(owner: str, repo: str, number: int) -> str:
    comments: list[dict] = []
    cursor = None
    discussion = None
    while True:
        variables: dict[str, Any] = {
            "owner": owner,
            "repo": repo,
            "number": number,
            "cursor": cursor,
        }
        payload = _gh_graphql(variables)
        discussion = (
            (payload.get("data") or {}).get("repository") or {}
        ).get("discussion")
        if not discussion:
            raise RuntimeError(f"discussion {owner}/{repo}#{number} not found")
        conn = discussion.get("comments") or {}
        for node in conn.get("nodes") or []:
            comments.append(
                {
                    "user": {"login": ((node.get("author") or {}).get("login")) or "unknown"},
                    "body": node.get("body") or "",
                }
            )
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
        if not cursor:
            break
    root = {
        "user": {"login": ((discussion.get("author") or {}).get("login")) or "op"},
        "body": discussion.get("body") or "",
    }
    return compose_markdown(root, comments, [])


def fetch_one(item: dict[str, str]) -> str:
    """Return composed Markdown for one GITHUB_SOURCES entry."""
    kind = item["kind"]
    owner = item["owner"]
    repo = item["repo"]
    number = int(item["number"])
    if kind == "discussion":
        return fetch_discussion_markdown(owner, repo, number)
    if kind == "pr":
        root = _gh_api(f"repos/{owner}/{repo}/pulls/{number}")
        comments = _gh_api_list(f"repos/{owner}/{repo}/issues/{number}/comments")
        review = _gh_api_list(f"repos/{owner}/{repo}/pulls/{number}/comments")
        return compose_markdown(root, comments, review)
    root = _gh_api(f"repos/{owner}/{repo}/issues/{number}")
    comments = _gh_api_list(f"repos/{owner}/{repo}/issues/{number}/comments")
    return compose_markdown(root, comments, [])


def _update_download_summary(results: list[dict]) -> None:
    summary_path = RAW_DIR / "download_summary.json"
    existing: list[dict] = []
    if summary_path.is_file():
        existing = json.loads(summary_path.read_text(encoding="utf-8"))
    by_url = {str(row.get("url")): row for row in existing}
    for row in results:
        by_url[str(row["url"])] = row
        # Drop the old HTML snapshot row if slug changed.
        old_html = str(row["slug"]).removesuffix(".md") + ".html"
        for key, prev in list(by_url.items()):
            if prev.get("slug") == old_html and key != row["url"]:
                del by_url[key]
            elif prev.get("slug") == old_html and key == row["url"]:
                by_url[key] = row
    summary_path.write_text(
        json.dumps(list(by_url.values()), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def download_all() -> list[dict]:
    """Fetch every GITHUB_SOURCES item, write .md, delete matching .html."""
    results: list[dict] = []
    for item in GITHUB_SOURCES:
        dest_dir = RAW_DIR / item["category"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / item["slug"]
        try:
            markdown = fetch_one(item)
            dest.write_text(markdown, encoding="utf-8")
            html_twin = dest.with_suffix(".html")
            if html_twin.is_file():
                html_twin.unlink()
            row = {
                "url": item["url"],
                "category": item["category"],
                "slug": item["slug"],
                "status": 200,
                "size": dest.stat().st_size,
                "path": f"{item['category']}/{item['slug']}",
            }
            print(f"OK  {item['category']}/{item['slug']} ({row['size']} bytes)")
        except Exception as exc:  # noqa: BLE001
            row = {
                "url": item["url"],
                "category": item["category"],
                "slug": item["slug"],
                "status": 0,
                "error": str(exc),
            }
            print(f"ERR {item['category']}/{item['slug']}: {exc}", file=sys.stderr)
        results.append(row)
    _update_download_summary(results)
    return results


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    results = download_all()
    failed = [r for r in results if r.get("status") != 200]
    if failed:
        print(f"{len(failed)} GitHub download(s) failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
