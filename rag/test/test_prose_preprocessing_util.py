"""Unit tests for ``rag/build/prose_preprocessing_util``.

These tests never touch the real vault. Each case builds a tiny input in
memory (or via ``tmp_path``) so a failure points at one function, not at
the 1.4 MB Sphinx HTML dump.

If you are new to pytest: a function named ``test_*`` is one case; a
``tmp_path`` argument is a fresh temporary directory pytest creates for
that case; ``assert`` is the only check you need.
"""

from __future__ import annotations

from prose_preprocessing_util.filters import (
    boilerplate_filter,
    github_noise_filter,
    length_filter,
    load_boilerplate_patterns,
    signature_density_filter,
)
from prose_preprocessing_util.heading_path import HeadingPath
from prose_preprocessing_util.ir import (
    ProseBlock,
    ProseDocument,
    assign_block_ids,
    make_doc_id,
    read_blocks_jsonl,
    read_ir,
    write_blocks_jsonl,
    write_ir,
)
from prose_preprocessing_util.parsers import parse_html, parse_markdown, parse_rst
from prose_preprocessing_util.review_queue import ReviewItem, append_queue, read_queue
from prose_preprocessing_util.selectors import (
    combine_select,
    heading_allowlist_select,
    heading_denylist_select,
    keyword_allowlist_select,
    maintainer_select,
    topic_map_select,
)


def _block(
    text: str,
    *,
    type_: str = "paragraph",
    heading_path: list[str] | None = None,
    block_id: str = "b0001",
    **kwargs,
) -> ProseBlock:
    return ProseBlock(
        block_id=block_id,
        type=type_,
        text=text,
        heading_path=heading_path or ["Root"],
        **kwargs,
    )


# --- heading_path -----------------------------------------------------------


def test_heading_path_enter_pops_sibling_and_deeper() -> None:
    hp = HeadingPath()
    hp.enter("GDScript reference", 1)
    hp.enter("Annotations", 2)
    assert hp.current() == ["GDScript reference", "Annotations"]
    hp.enter("Comments", 2)  # sibling replaces Annotations
    assert hp.current() == ["GDScript reference", "Comments"]
    hp.enter("GDScript reference", 1)  # new top-level
    assert hp.current() == ["GDScript reference"]


def test_heading_path_exit() -> None:
    hp = HeadingPath()
    hp.enter("A", 1)
    hp.enter("B", 2)
    hp.enter("C", 3)
    hp.exit(2)
    assert hp.current() == ["A"]


# --- IR I/O -----------------------------------------------------------------


def test_make_doc_id_and_roundtrip(tmp_path) -> None:
    assert make_doc_id("rst", "gdscript_basics.rst") == "rst/gdscript_basics.rst"
    doc = ProseDocument(
        doc_id="rst/gdscript_basics.rst",
        source="official_doc",
        source_file="gdscript_basics.rst",
        source_type="rst",
        keep=True,
        blocks=[_block("hello", block_id="b0001")],
    )
    path = tmp_path / "gdscript_basics.rst.ir.json"
    write_ir(doc, path)
    loaded = read_ir(path)
    assert loaded.doc_id == doc.doc_id
    assert loaded.blocks[0].text == "hello"


def test_blocks_jsonl_roundtrip_and_ids(tmp_path) -> None:
    blocks = assign_block_ids(
        [_block("one", block_id="x"), _block("two", type_="code", block_id="y")]
    )
    assert [b.block_id for b in blocks] == ["b0001", "b0002"]
    path = tmp_path / "file.rst.blocks.jsonl"
    write_blocks_jsonl(blocks, path)
    loaded = read_blocks_jsonl(path)
    assert [b.text for b in loaded] == ["one", "two"]


# --- filters ----------------------------------------------------------------


def test_length_filter_keeps_short_code_and_headings() -> None:
    blocks = [
        _block("hi", block_id="b0001"),  # too short
        _block("@export var speed := 0", type_="code", block_id="b0002"),
        _block("Await", type_="heading", block_id="b0003"),
        _block("This paragraph is definitely longer than forty characters.", block_id="b0004"),
    ]
    kept = length_filter(blocks, 40)
    assert [b.block_id for b in kept] == ["b0002", "b0003", "b0004"]


def test_boilerplate_filter_and_loader(tmp_path) -> None:
    path = tmp_path / "boilerplate_patterns.txt"
    path.write_text("# comment\nWas this page helpful\\?\nLast updated on\n", encoding="utf-8")
    patterns = load_boilerplate_patterns(path)
    blocks = [
        _block("Was this page helpful?", block_id="b0001"),
        _block("Useful migration note about await.", block_id="b0002"),
    ]
    kept = boilerplate_filter(blocks, patterns)
    assert [b.block_id for b in kept] == ["b0002"]


def test_signature_density_filter_drops_api_tables() -> None:
    table = _block(
        "void close() FileAccess create_temp(mode_flags: ModeFlags) static bool eof_reached() const",
        heading_path=["FileAccess", "Methods"],
        block_id="b0001",
    )
    prose = _block(
        "This class can be used to permanently store data in the user device file system.",
        heading_path=["FileAccess", "Description"],
        block_id="b0002",
    )
    kept = signature_density_filter([table, prose], 0.5)
    assert [b.block_id for b in kept] == ["b0002"]


def test_github_noise_filter() -> None:
    blocks = [
        _block("+1", block_id="b0001"),
        _block("Thanks!", block_id="b0002"),
        _block("Any update?", block_id="b0003"),
        _block("Tweens are no longer nodes; they are fire-and-forget objects.", block_id="b0004"),
    ]
    kept = github_noise_filter(blocks)
    assert [b.block_id for b in kept] == ["b0004"]


# --- selectors --------------------------------------------------------------


def test_heading_allow_deny_and_combine() -> None:
    history = _block("moved", heading_path=["GDScript reference", "History"], block_id="b0001")
    anno = _block(
        "Annotations are special tokens.",
        heading_path=["GDScript reference", "Annotations"],
        block_id="b0002",
    )
    other = _block("style note", heading_path=["GDScript reference", "Comments"], block_id="b0003")
    blocks = [history, anno, other]
    den = heading_denylist_select(blocks, ["History"])
    allow = heading_allowlist_select(blocks, ["Annotations"])
    keep, drop, uncertain = combine_select(den, allow)
    assert [b.block_id for b in drop] == ["b0001"]
    assert [b.block_id for b in keep] == ["b0002"]
    assert [b.block_id for b in uncertain] == ["b0003"]


def test_keyword_topic_maintainer_select() -> None:
    await_blk = _block("Use await instead of yield.", block_id="b0001")
    keep, _, _ = keyword_allowlist_select([await_blk], ["await"])
    assert keep == [await_blk]

    os_blk = _block("OS was split.", heading_path=["OS / DisplayServer split"], block_id="b0002")
    keep, _, _ = topic_map_select([os_blk], {"topics": ["OS", "RPC"]})
    assert keep == [os_blk]

    maint = _block("design note", subtype="akien-mga", block_id="b0003")
    other = _block("+1 from me", subtype="random-user", block_id="b0004")
    keep, _, uncertain = maintainer_select([maint, other], ["akien-mga"])
    assert keep == [maint]
    assert uncertain == [other]


# --- parsers ----------------------------------------------------------------


def test_parse_rst_emits_heading_paragraph_code_admonition() -> None:
    rst = """\
Demo title
==========

Annotations
-----------

Annotations are extra information for the interpreter and are definitely long enough.

::

    @export var speed := 0

.. warning::

    Using @onready and @export together triggers ONREADY_WITH_EXPORT.
"""
    blocks = parse_rst(rst, "demo.rst")
    types = [b.type for b in blocks]
    assert "heading" in types
    assert "paragraph" in types
    assert "code" in types
    assert "admonition" in types
    onready = [b for b in blocks if "ONREADY_WITH_EXPORT" in b.text]
    assert onready
    assert "Annotations" in onready[0].heading_path


def test_parse_html_godot_blog_profile() -> None:
    html = """
    <html><body>
    <nav>Donate</nav>
    <div class="article-body">
      <h3>OS / DisplayServer split</h3>
      <p>One of the largest singletons in Godot is the OS class, which grew too large.</p>
      <pre><code>DisplayServer.window_set_mode()</code></pre>
    </div>
    <footer>Privacy policy</footer>
    </body></html>
    """
    blocks = parse_html(html, "godot_blog")
    assert any(b.type == "heading" and "DisplayServer" in b.text for b in blocks)
    assert any(b.type == "paragraph" and "OS class" in b.text for b in blocks)
    assert any(b.type == "code" for b in blocks)
    assert not any("Donate" in b.text or "Privacy" in b.text for b in blocks)


def test_parse_html_sphinx_skips_method_tables() -> None:
    html = """
    <div role="main">
      <div itemprop="articleBody">
        <section id="fileaccess">
          <h1>FileAccess</h1>
          <section id="description">
            <h2>Description</h2>
            <p>This class can be used to permanently store data in the user device file system.</p>
          </section>
          <section class="classref-reftable-group" id="methods">
            <h2>Methods</h2>
            <table><tr><td>void</td><td>close()</td></tr></table>
          </section>
        </section>
      </div>
    </div>
    """
    blocks = parse_html(html, "sphinx")
    texts = " ".join(b.text for b in blocks)
    assert "permanently store data" in texts
    assert "close()" not in texts


def test_parse_real_gdscript_basics_keeps_onready() -> None:
    """Sanity check against the actual vault RST (not a fixture)."""
    from pathlib import Path

    rst_path = (
        Path(__file__).resolve().parent.parent
        / "vault"
        / "tier_b_prose"
        / "_raw"
        / "official_gdscript_doc"
        / "gdscript_basics.rst"
    )
    if not rst_path.exists():
        return
    blocks = parse_rst(rst_path.read_text(encoding="utf-8"), str(rst_path))
    assert any("ONREADY_WITH_EXPORT" in b.text for b in blocks)
    assert any(b.type == "heading" and "Annotations" in b.text for b in blocks)


def test_parse_markdown_headings_fences_lists() -> None:
    md = """# body by reduz

Tweens are no longer nodes.

```gdscript
var tween := get_tree().create_tween()
```

- fire and forget
- chained by default
"""
    blocks = parse_markdown(md)
    assert blocks[0].type == "heading"
    assert blocks[0].subtype == "reduz"
    assert any(b.type == "code" and "create_tween" in b.text for b in blocks)
    assert any(b.type == "list" and "fire and forget" in b.text for b in blocks)


# --- review queue -----------------------------------------------------------


def test_review_queue_append_and_read(tmp_path) -> None:
    path = tmp_path / "review_queue.jsonl"
    items = [
        ReviewItem(
            doc_id="community_blog/await.html",
            block_id="b0012",
            text="await in _process",
            proposed="keep",
            channel="heuristic",
            reason="keyword_allowlist: await+_process",
        )
    ]
    append_queue(path, items)
    append_queue(path, items)
    loaded = read_queue(path)
    assert len(loaded) == 2
    assert loaded[0].reason.startswith("keyword_allowlist")
