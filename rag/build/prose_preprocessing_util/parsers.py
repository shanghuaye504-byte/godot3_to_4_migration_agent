"""Format normalizers: RST / HTML / Markdown -> typed blocks.

These functions only do structural parsing and heading_path tracking.
They do NOT apply policy filters or select keep/drop.
Specification: rag/vault/tier_b_prose/CHUNKING.md §4.4 and §5
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from docutils.nodes import (  # type: ignore[import-untyped]
    NodeVisitor,
    SkipNode,
    section,
    title as rst_title,
)

from .heading_path import HeadingPath
from .ir import ProseBlock, assign_block_ids

_BUILD_DIR = Path(__file__).resolve().parent.parent
if str(_BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(_BUILD_DIR))

from parse_upgrading_docs import inject_substitution_defs, parse_doctree  # noqa: E402

_HEADING_STRIP_RE = re.compile(r"[\u00b6\uF0B6]+")
_FENCE_RE = re.compile(r"^```(\w*)\s*$")
_ATX_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_LOGIN_HEADING_RE = re.compile(
    r"^(?:body|comment|discussion)\s+by\s+(\S+)\s*$",
    re.IGNORECASE,
)
_UL_RE = re.compile(r"^(\s*)([-*+])\s+(.*)$")
_OL_RE = re.compile(r"^(\s*)(\d+[.)])\s+(.*)$")
_DOCUTILS_NOISE = [
    re.compile(r".*:\s*\(INFO/\d+\) No role entry for"),
    re.compile(r".*:\s*\(ERROR/\d+\) Unknown interpreted text role"),
    re.compile(r'Trying "[^"]+" as canonical role name\.'),
]


def _strip_docutils_noise(text: str) -> str:
    lines = [ln for ln in text.splitlines() if not any(p.search(ln) for p in _DOCUTILS_NOISE)]
    return "\n".join(lines).strip()


def parse_rst(rst_text: str, source_path: str) -> list[ProseBlock]:
    """Parse RST into typed blocks using docutils.

    Reuses ``inject_substitution_defs`` and ``parse_doctree`` from
    ``parse_upgrading_docs.py`` so Godot substitution (``|✔️|``) and Sphinx
    roles fail open the same way the A-layer parser already does.
    """
    prepared = inject_substitution_defs(rst_text)
    document = parse_doctree(prepared, source_path)
    visitor = _RstBlockVisitor(document)
    document.walkabout(visitor)
    return assign_block_ids(visitor.blocks)


def parse_html(html_text: str, profile: str) -> list[ProseBlock]:
    """Parse HTML into typed blocks.

    ``profile``:
      - ``sphinx``: official_html_doc (type C)
      - ``godot_blog``: official_blog (type D)
      - ``community``: community_blog / community_gist
    """
    try:
        from bs4 import BeautifulSoup, NavigableString, Tag
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "beautifulsoup4 is required to parse HTML. "
            "Install the build extra: uv sync --group build"
        ) from exc

    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    if profile == "sphinx":
        root = _sphinx_root(soup)
        blocks = _walk_html(root, skip_reftables=True)
    elif profile == "godot_blog":
        root = soup.select_one("div.article-body") or soup.select_one("article")
        blocks = _walk_html(root)
    elif profile == "community":
        blocks = _parse_community_html(soup)
    else:
        raise ValueError(
            f"unknown HTML profile {profile!r}; expected sphinx, godot_blog, or community"
        )

    if len(blocks) < 3:
        fallback = _trafilatura_blocks(html_text)
        if len(fallback) > len(blocks):
            blocks = fallback
    return assign_block_ids(blocks)


def parse_markdown(md_text: str) -> list[ProseBlock]:
    """Parse Markdown (GitHub API body) into typed blocks."""
    blocks: list[ProseBlock] = []
    hp = HeadingPath()
    lines = md_text.replace("\r\n", "\n").split("\n")
    i = 0
    para: list[str] = []
    list_items: list[str] = []
    in_fence = False
    fence_lang = ""
    fence_lines: list[str] = []

    def flush_para() -> None:
        nonlocal para
        text = "\n".join(para).strip()
        para = []
        if text:
            blocks.append(
                _draft("paragraph", text, list(hp.current()))
            )

    def flush_list() -> None:
        nonlocal list_items
        if not list_items:
            return
        text = "\n".join(list_items).strip()
        list_items = []
        if text:
            blocks.append(_draft("list", text, list(hp.current())))

    while i < len(lines):
        line = lines[i]
        fence_match = _FENCE_RE.match(line.strip())
        if fence_match:
            flush_para()
            flush_list()
            if in_fence:
                blocks.append(
                    _draft(
                        "code",
                        "\n".join(fence_lines).rstrip(),
                        list(hp.current()),
                        language=fence_lang or None,
                    )
                )
                fence_lines = []
                fence_lang = ""
                in_fence = False
            else:
                in_fence = True
                fence_lang = fence_match.group(1) or ""
            i += 1
            continue
        if in_fence:
            fence_lines.append(line)
            i += 1
            continue

        atx = _ATX_RE.match(line)
        if atx:
            flush_para()
            flush_list()
            level = len(atx.group(1))
            title = atx.group(2).strip()
            parent = hp.current()
            login_hit = _LOGIN_HEADING_RE.match(title)
            blocks.append(
                _draft(
                    "heading",
                    title,
                    list(parent),
                    level=level,
                    subtype=login_hit.group(1) if login_hit else None,
                )
            )
            hp.enter(title, level)
            i += 1
            continue

        if line.startswith(">"):
            flush_para()
            flush_list()
            quote_lines = []
            while i < len(lines) and lines[i].startswith(">"):
                quote_lines.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
            text = "\n".join(quote_lines).strip()
            if text:
                blocks.append(_draft("quote", text, list(hp.current())))
            continue

        ul = _UL_RE.match(line)
        ol = _OL_RE.match(line)
        if ul or ol:
            flush_para()
            item = (ul or ol).group(3).strip()  # type: ignore[union-attr]
            list_items.append(f"- {item}")
            i += 1
            continue

        if not line.strip():
            flush_para()
            flush_list()
            i += 1
            continue

        if list_items:
            # continuation of a list item
            list_items[-1] = list_items[-1] + " " + line.strip()
            i += 1
            continue

        para.append(line.rstrip())
        i += 1

    if in_fence and fence_lines:
        blocks.append(
            _draft(
                "code",
                "\n".join(fence_lines).rstrip(),
                list(hp.current()),
                language=fence_lang or None,
            )
        )
    flush_para()
    flush_list()
    return assign_block_ids(blocks)


def _draft(
    type_: str,
    text: str,
    heading_path: list[str],
    *,
    level: int | None = None,
    language: str | None = None,
    subtype: str | None = None,
) -> ProseBlock:
    return ProseBlock(
        block_id="b0000",
        type=type_,
        text=text,
        heading_path=heading_path,
        level=level,
        language=language,
        subtype=subtype,
    )


def _section_level(node) -> int:
    level = 1
    parent = node.parent
    while parent is not None:
        if isinstance(parent, section):
            level += 1
        parent = parent.parent
    return level


def _section_title_text(node) -> str:
    for child in node.children:
        if isinstance(child, rst_title):
            return child.astext().strip()
    return ""


class _RstBlockVisitor(NodeVisitor):
    def __init__(self, document) -> None:
        super().__init__(document)
        self.hp = HeadingPath()
        self.blocks: list[ProseBlock] = []

    def visit_section(self, node):
        title = _section_title_text(node)
        level = _section_level(node)
        if title:
            parent = self.hp.current()
            self.blocks.append(
                _draft("heading", title, list(parent), level=level)
            )
            self.hp.enter(title, level)

    def depart_section(self, node):
        level = _section_level(node)
        self.hp.exit(level)

    def visit_paragraph(self, node):
        text = _strip_docutils_noise(node.astext())
        if text:
            self.blocks.append(_draft("paragraph", text, list(self.hp.current())))
        raise SkipNode

    def visit_literal_block(self, node):
        text = node.astext().rstrip("\n")
        language = None
        classes = node.get("classes") or []
        for cls in classes:
            if cls not in {"code", "literal-block"}:
                language = cls
                break
        self.blocks.append(
            _draft("code", text, list(self.hp.current()), language=language)
        )
        raise SkipNode

    visit_doctest_block = visit_literal_block

    def visit_admonition(self, node):
        self._emit_admonition(node, subtype="admonition")
        raise SkipNode

    def visit_note(self, node):
        self._emit_admonition(node, subtype="note")
        raise SkipNode

    def visit_warning(self, node):
        self._emit_admonition(node, subtype="warning")
        raise SkipNode

    def visit_danger(self, node):
        self._emit_admonition(node, subtype="danger")
        raise SkipNode

    def visit_attention(self, node):
        self._emit_admonition(node, subtype="attention")
        raise SkipNode

    def visit_caution(self, node):
        self._emit_admonition(node, subtype="caution")
        raise SkipNode

    def visit_important(self, node):
        self._emit_admonition(node, subtype="important")
        raise SkipNode

    def visit_tip(self, node):
        self._emit_admonition(node, subtype="tip")
        raise SkipNode

    def visit_hint(self, node):
        self._emit_admonition(node, subtype="hint")
        raise SkipNode

    def _emit_admonition(self, node, subtype: str) -> None:
        text = node.astext().strip()
        if text:
            self.blocks.append(
                _draft(
                    "admonition",
                    text,
                    list(self.hp.current()),
                    subtype=subtype,
                )
            )

    def visit_bullet_list(self, node):
        self._emit_list(node)
        raise SkipNode

    def visit_enumerated_list(self, node):
        self._emit_list(node)
        raise SkipNode

    def _emit_list(self, node) -> None:
        items = []
        for child in node.children:
            text = child.astext().strip()
            if text:
                items.append(f"- {text}")
        if items:
            self.blocks.append(
                _draft("list", "\n".join(items), list(self.hp.current()))
            )

    def visit_block_quote(self, node):
        text = node.astext().strip()
        if text:
            self.blocks.append(_draft("quote", text, list(self.hp.current())))
        raise SkipNode

    def visit_system_message(self, node):
        raise SkipNode

    def visit_comment(self, node):
        raise SkipNode

    def visit_table(self, node):
        # Language-reference tables (keyword lists, operator precedence) are
        # not migration prose. Skip them; A-layer already structured the
        # upgrading-guide tables separately.
        raise SkipNode

    def unknown_visit(self, node):
        return

    def unknown_departure(self, node):
        return


def _clean_heading(text: str) -> str:
    text = _HEADING_STRIP_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _sphinx_root(soup):
    main = soup.select_one('[role="main"]')
    if main is None:
        return soup
    body = main.select_one('[itemprop="articleBody"]')
    return body or main


def _parse_community_html(soup) -> list[ProseBlock]:
    gist_lines = soup.select("td.js-file-line")
    if gist_lines:
        joined = "\n".join(el.get_text() for el in gist_lines)
        return parse_markdown(joined)

    comments = soup.select(".comment-body.markdown-body")
    if comments:
        blocks: list[ProseBlock] = []
        for i, comment in enumerate(comments):
            author = _nearest_author(comment) or f"comment-{i}"
            hp = HeadingPath()
            parent: list[str] = []
            blocks.append(
                _draft("heading", author, parent, level=1, subtype=author)
            )
            hp.enter(author, 1)
            blocks.extend(
                _walk_html_from(comment, hp, skip_reftables=False, author=author)
            )
        return blocks

    root = (
        soup.select_one("div.article-body")
        or soup.select_one("article")
        or soup.select_one("main")
        or soup.select_one('[itemprop="articleBody"]')
        or soup.body
    )
    return _walk_html(root)


def _nearest_author(comment) -> str | None:
    node = comment
    for _ in range(10):
        if node is None:
            break
        author = node.select_one("a.author")
        if author is not None:
            login = author.get_text(" ", strip=True)
            if login:
                return login
        node = node.parent
    return None


def _walk_html(root, *, skip_reftables: bool = False) -> list[ProseBlock]:
    if root is None:
        return []
    hp = HeadingPath()
    return _walk_html_from(root, hp, skip_reftables=skip_reftables)


def _walk_html_from(
    root,
    hp: HeadingPath,
    *,
    skip_reftables: bool,
    author: str | None = None,
) -> list[ProseBlock]:
    from bs4 import NavigableString, Tag

    blocks: list[ProseBlock] = []

    def visit(el) -> None:
        if isinstance(el, NavigableString):
            return
        if not isinstance(el, Tag):
            return
        name = el.name.lower() if el.name else ""
        classes = el.get("class") or []
        class_str = " ".join(classes) if isinstance(classes, list) else str(classes)
        el_id = (el.get("id") or "") if hasattr(el, "get") else ""

        if name in {"script", "style", "nav", "footer", "header", "aside", "form"}:
            return
        if skip_reftables:
            if "classref-reftable-group" in class_str:
                return
            if el_id in {
                "tutorials",
                "properties",
                "methods",
                "enumerations",
                "signals",
                "constants",
            }:
                return

        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(name[1])
            title = _clean_heading(el.get_text(" ", strip=True))
            if not title:
                return
            parent = hp.current()
            blocks.append(
                _draft(
                    "heading",
                    title,
                    list(parent),
                    level=level,
                    subtype=author,
                )
            )
            hp.enter(title, level)
            return

        if name == "pre" or (name == "div" and "highlight" in class_str and el.find("pre")):
            pre = el if name == "pre" else el.find("pre")
            text = pre.get_text("", strip=False).strip("\n") if pre is not None else ""
            if text.strip():
                lang = None
                code = pre.find("code") if pre is not None else None
                if code is not None:
                    cc = code.get("class") or []
                    for cls in cc:
                        if cls.startswith("language-"):
                            lang = cls.split("-", 1)[-1]
                            break
                        if cls.startswith("highlight-"):
                            lang = cls.split("-", 1)[-1]
                            break
                blocks.append(
                    _draft(
                        "code",
                        text,
                        list(hp.current()),
                        language=lang,
                        subtype=author,
                    )
                )
            return

        if "admonition" in class_str:
            subtype = "admonition"
            for cls in classes:
                if cls != "admonition" and not cls.startswith("admonition-"):
                    subtype = cls
                    break
            text = el.get_text("\n", strip=True)
            if text:
                blocks.append(
                    _draft(
                        "admonition",
                        text,
                        list(hp.current()),
                        subtype=subtype,
                    )
                )
            return

        if name in {"ul", "ol"}:
            items = []
            for li in el.find_all("li", recursive=False):
                t = li.get_text(" ", strip=True)
                if t:
                    items.append(f"- {t}")
            if items:
                blocks.append(
                    _draft(
                        "list",
                        "\n".join(items),
                        list(hp.current()),
                        subtype=author,
                    )
                )
            return

        if name == "blockquote":
            text = el.get_text("\n", strip=True)
            if text:
                blocks.append(
                    _draft("quote", text, list(hp.current()), subtype=author)
                )
            return

        if name == "p":
            text = el.get_text(" ", strip=True)
            if text:
                blocks.append(
                    _draft(
                        "paragraph",
                        text,
                        list(hp.current()),
                        subtype=author,
                    )
                )
            return

        if name == "table":
            if skip_reftables:
                return
            rows = []
            for tr in el.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
                line = " | ".join(c for c in cells if c)
                if line:
                    rows.append(f"- {line}")
            if rows:
                blocks.append(
                    _draft("list", "\n".join(rows), list(hp.current()), subtype=author)
                )
            return

        for child in el.children:
            visit(child)

    visit(root)
    return blocks


def _trafilatura_blocks(html_text: str) -> list[ProseBlock]:
    try:
        import trafilatura
    except ImportError:
        return []
    extracted = trafilatura.extract(
        html_text,
        include_comments=False,
        include_tables=False,
        include_formatting=False,
        output_format="txt",
    )
    if not extracted:
        return []
    return parse_markdown(extracted)
