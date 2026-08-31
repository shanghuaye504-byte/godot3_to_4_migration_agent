"""Tests for the type-B/C/D/E/F process scripts and curation compiler.

``process_file`` is side-effect free (it returns a ``ProseDocument``).
``main()`` is what writes ``ir/*.ir.json``. Tests call ``process_file`` with
a JSONL fixture under ``tmp_path`` so they do not rewrite the real vault.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from prose_preprocessing_util.ir import ProseBlock, assign_block_ids, write_blocks_jsonl
from prose_preprocessing_util.parsers import parse_markdown

import compile_curation
import process_community
import process_github
import process_official_blog
import process_official_gdscript_doc
import process_official_html_doc
import scan_tier_b_raw


def _write_blocks(path: Path, blocks: list[ProseBlock]) -> Path:
    write_blocks_jsonl(blocks, path)
    return path


def _b(
    bid: str,
    text: str,
    *,
    type_: str = "paragraph",
    heading: list[str] | None = None,
    **kwargs,
) -> ProseBlock:
    return ProseBlock(
        block_id=bid,
        type=type_,
        text=text,
        heading_path=heading or ["Root"],
        **kwargs,
    )


def test_html_profile_for_bucket() -> None:
    assert scan_tier_b_raw.html_profile_for_bucket("official_html_doc") == "sphinx"
    assert scan_tier_b_raw.html_profile_for_bucket("official_blog") == "godot_blog"
    assert scan_tier_b_raw.html_profile_for_bucket("community_blog") == "community"
    try:
        scan_tier_b_raw.html_profile_for_bucket("github_pr")
        raise AssertionError("github buckets must not use an HTML profile")
    except ValueError:
        pass


def test_process_official_gdscript_keeps_annotations_drops_history(tmp_path) -> None:
    path = _write_blocks(
        tmp_path / "gdscript_basics.rst.blocks.jsonl",
        [
            _b("b0001", "GDScript reference", type_="heading", heading=[]),
            _b(
                "b0002",
                "History documentation was moved to the FAQ.",
                heading=["GDScript reference", "History"],
            ),
            _b("b0003", "Annotations", type_="heading", heading=["GDScript reference"]),
            _b(
                "b0004",
                "Annotations are extra information given to the interpreter and they matter.",
                heading=["GDScript reference", "Annotations"],
            ),
            _b(
                "b0005",
                "Therefore the ONREADY_WITH_EXPORT warning is generated.",
                heading=["GDScript reference", "Annotations"],
            ),
            _b(
                "b0006",
                "@onready @export var b = 1",
                type_="code",
                heading=["GDScript reference", "Annotations"],
                language="gdscript",
            ),
        ],
    )
    doc = process_official_gdscript_doc.process_file(path)
    assert doc is not None
    assert doc.source == "official_doc"
    assert doc.source_type == "rst"
    texts = " ".join(b.text for b in doc.blocks)
    assert "ONREADY_WITH_EXPORT" in texts
    assert "Annotations are extra information" in texts
    assert "History documentation" not in texts


def test_process_official_html_drops_signature_keeps_description(tmp_path) -> None:
    path = _write_blocks(
        tmp_path / "class_fileaccess.html.blocks.jsonl",
        [
            _b("b0001", "FileAccess", type_="heading", heading=[]),
            _b(
                "b0002",
                "This class can be used to permanently store data in the user device file system.",
                heading=["FileAccess", "Description"],
            ),
            _b(
                "b0003",
                "void close() static FileAccess open(path: String, flags: ModeFlags) const bool eof_reached()",
                heading=["FileAccess", "Methods"],
            ),
            _b(
                "b0004",
                "func save():\n    FileAccess.open(path, FileAccess.WRITE)",
                type_="code",
                heading=["FileAccess", "Description"],
            ),
        ],
    )
    doc = process_official_html_doc.process_file(path)
    assert doc is not None
    texts = " ".join(b.text for b in doc.blocks)
    assert "permanently store data" in texts
    assert "eof_reached" not in texts
    assert any(b.type == "code" for b in doc.blocks)


def test_process_official_blog_keeps_os_topic_drops_future(tmp_path) -> None:
    path = _write_blocks(
        tmp_path / "core-refactoring-progress-report-2.html.blocks.jsonl",
        [
            _b("b0001", "Core refactoring", type_="heading", heading=[]),
            _b(
                "b0002",
                "OS / DisplayServer split",
                type_="heading",
                heading=["Core refactoring"],
            ),
            _b(
                "b0003",
                "One of the largest singletons in Godot is the OS class, which made headless multi-window support impossible.",
                heading=["Core refactoring", "OS / DisplayServer split"],
            ),
            _b("b0004", "Future", type_="heading", heading=["Core refactoring"]),
            _b(
                "b0005",
                "Please consider becoming our patron so we can ship the next release plan faster than ever before.",
                heading=["Core refactoring", "Future"],
            ),
        ],
    )
    doc = process_official_blog.process_file(path)
    assert doc is not None
    texts = " ".join(b.text for b in doc.blocks)
    assert "OS class" in texts
    assert "patron" not in texts


def test_process_github_keeps_opening_post(tmp_path) -> None:
    path = _write_blocks(
        tmp_path / "godot-docs_issue_6265.md.blocks.jsonl",
        [
            _b("b0001", "Uh oh!", type_="heading", heading=[]),
            _b("b0002", "There was an error while loading. Please reload this page .", heading=["Uh oh!"]),
            _b(
                "b0003",
                "body by TheYellowArchitect",
                type_="heading",
                heading=[],
                subtype="TheYellowArchitect",
            ),
            _b(
                "b0004",
                "Basically, convert the above setget to use set and get in Godot 4.",
                heading=["body by TheYellowArchitect"],
            ),
        ],
    )
    items = process_github.process_file(path, "github_issue")
    assert items
    texts = " ".join(item.text for item in items)
    assert "convert the above setget" in texts
    assert "Please reload" not in texts


def test_process_github_keeps_maintainer_and_code(tmp_path) -> None:
    path = _write_blocks(
        tmp_path / "godot_pull_41794.md.blocks.jsonl",
        [
            _b("b0001", "+1", heading=["comment by random"], subtype="random"),
            _b(
                "b0002",
                "Tweens are no longer nodes. They are References designed in a fire and forget manner.",
                heading=["comment by reduz"],
                subtype="reduz",
            ),
            _b(
                "b0003",
                "var tween := get_tree().create_tween()",
                type_="code",
                heading=["comment by somebody"],
                subtype="somebody",
            ),
        ],
    )
    items = process_github.process_file(path, "github_pr")
    assert items
    assert all(item.doc_id.startswith("github_pr/") for item in items)
    texts = " ".join(item.text for item in items)
    assert "fire and forget" in texts
    assert "create_tween" in texts
    assert "+1" not in texts


def test_process_github_from_composed_markdown(tmp_path) -> None:
    md = """# body by KoBeWi

Tweens are no longer nodes.

## comment by random

+1

## comment by reduz

They are References designed in a fire and forget manner.

## comment by somebody

```gdscript
var tween := get_tree().create_tween()
```
"""
    path = tmp_path / "godot_pull_41794.md.blocks.jsonl"
    write_blocks_jsonl(assign_block_ids(parse_markdown(md)), path)
    items = process_github.process_file(path, "github_pr")
    assert items
    texts = " ".join(item.text for item in items)
    assert "Tweens are no longer nodes" in texts
    assert "fire and forget" in texts
    assert "create_tween" in texts
    assert "+1" not in texts
    heading = next(b for b in parse_markdown(md) if b.type == "heading")
    assert heading.subtype == "KoBeWi"


def test_process_community_writes_queue_not_ir(tmp_path, monkeypatch) -> None:
    queue = tmp_path / "prose_review_queue.jsonl"
    monkeypatch.setattr(process_community, "QUEUE_PATH", queue)
    monkeypatch.setattr(process_community, "PREPROCESS_DIR", tmp_path)
    monkeypatch.setattr(process_community, "POLICY_DIR", process_community.POLICY_DIR)
    bucket_dir = tmp_path / "community_blog"
    bucket_dir.mkdir()
    _write_blocks(
        bucket_dir / "await-coroutine-basics.html.blocks.jsonl",
        [
            _b(
                "b0001",
                "Using await every frame inside _process is a silent failure that looks like Godot 4 is not working.",
                heading=["Migrating from Godot 3's yield"],
            ),
            _b("b0002", "Subscribe to our newsletter today for more tips.", heading=["Footer"]),
        ],
    )
    n = process_community.process_bucket("community_blog", [])
    assert n >= 1
    assert queue.exists()
    assert not list(tmp_path.rglob("*.ir.json"))


def test_compile_curation_builds_paragraph_and_code(tmp_path, monkeypatch) -> None:
    data = {
        "source_file": "await-coroutine-basics.html",
        "source_url": "https://example.com/await",
        "source": "community_prose",
        "source_type": "community_blog",
        "since_version": "4.0",
        "confidence": "needs_review",
        "title": "Await coroutine basics",
        "match_tokens": ["yield", "await", "_process"],
        "excerpts": [
            {
                "heading_path": ["Migrating from Godot 3's yield"],
                "text": "Do not await inside _process every frame or coroutines pile up.",
                "code": "func _process(delta):\n    await something",
                "language": "gdscript",
            }
        ],
    }
    doc = compile_curation.build_ir(data)
    assert doc.keep is True
    assert doc.confidence == "needs_review"
    assert [b.type for b in doc.blocks] == ["paragraph", "code"]
    assert doc.blocks[1].language == "gdscript"
    assert doc.match_tokens == ["yield", "await", "_process"]

    curation_dir = tmp_path / "curation"
    curation_dir.mkdir()
    yaml_path = curation_dir / "await-coroutine-basics.yaml"
    yaml_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.setattr(compile_curation, "CURATION_DIR", curation_dir)
    monkeypatch.setattr(compile_curation, "OUTPUT_DIR", tmp_path / "ir")
    assert compile_curation.main() == 0
    written = tmp_path / "ir" / "community_blog" / "await-coroutine-basics.ir.json"
    assert written.exists()
