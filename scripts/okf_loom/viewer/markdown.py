"""Small pure-Python Markdown renderer for the OKF viewer.

Scope: the subset used in OKF bundles — headings, paragraphs, unordered /
ordered lists (incl. nested), blockquotes, fenced code blocks, inline code,
GFM-style tables, links, emphasis + strong, horizontal rules. This is NOT
a full CommonMark implementation; it is a deliberate minimal subset (no
markdown package dependency, per the hard constraints).

Raw HTML is ESCAPED, not passed through. All link ``href`` and image
``src`` attributes pass through a URL-scheme allowlist (see
``_safe_url``); ``javascript:``, ``data:``, ``vbscript:``, and other
dangerous schemes are neutralised.

Two entry points:

* :func:`markdown_to_html` — pure text→HTML, links rendered verbatim.
* :func:`rewrite_internal_links` — post-process rendered HTML, replacing
  ``<a href="<internal>">`` with the viewer's per-mode URL form using a
  precomputed ``target_raw → url`` map (the Graph already resolved the
  target concept id, so the caller builds the map from ``Graph.out_edges``).

Why split: the renderer stays free of Bundle/Graph coupling (so it can be
unit-tested in isolation), and link rewriting is a single policy applied
identically by ``render.py`` (static / single-file data) and ``server.py``.
"""
from __future__ import annotations

import html as _html
import posixpath
import re
from typing import Iterator, Mapping

from ..paths import ConceptId, concept_id_to_str

# ---------------------------------------------------------------------------
# Block-level scanner
# ---------------------------------------------------------------------------

# P1-1 (iter-8): CommonMark §4.5 defines BOTH ``` and ~~~ as code fences.
# parse.py:_FENCE_RE already handles both; the renderer must match.
_FENCE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<fence>```+|~~~+)(?P<lang>[^\n]*)\n(?P<code>.*?)\n[ \t]*(?P=fence)[ \t]*$",
    re.DOTALL | re.MULTILINE,
)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)(?:\s+#+)?$", re.MULTILINE)
_HR_RE = re.compile(r"^[ \t]*(-{3,}|\*{3,}|_{3,})[ \t]*$", re.MULTILINE)
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")

# Anchors / fragment links (passed through untouched).
_LINK_HREF_RE = re.compile(r'(<a\s+[^>]*?)href=("|\')(?P<href>[^"\']+)\2', re.IGNORECASE)


def _slugify(text: str) -> str:
    text = _html.unescape(text).lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text or "section"


# ---------------------------------------------------------------------------
# Inline formatting
# ---------------------------------------------------------------------------

_INLINE_CODE_RE = re.compile(r"`(?P<s>[^`]+)`")
_EMPH_RES: list[tuple[re.Pattern[str], str]] = [
    # Strong first (longest match), then emphasis.
    (re.compile(r"\*\*(.+?)\*\*"), "<strong>\\1</strong>"),
    (re.compile(r"__(.+?)__"), "<strong>\\1</strong>"),
    (re.compile(r"(?<![\w*])\*(?!\s)([^*\n]+?)\*(?![\w*])"), "<em>\\1</em>"),
    (re.compile(r"(?<![\w_])_(?!\s)([^_\n]+?)_(?![\w_])"), "<em>\\1</em>"),
]


def _render_inline(text: str) -> str:
    """Render inline markdown to HTML.

    Inline code spans are extracted first into placeholders so emphasis /
    link regexes never touch their contents, then restored at the end.
    """
    stash: list[str] = []

    def _stash_code(m: re.Match[str]) -> str:
        body = m.group("s")
        rendered = f'<code>{_escape(body)}</code>'
        token = f"\x01{len(stash)}\x01"
        stash.append(rendered)
        return token

    # Pull out inline code.
    text = _INLINE_CODE_RE.sub(_stash_code, text)

    # Escape the rest.
    text = _escape(text, escape_quotes=False)

    # Links: [label](href "title?")
    def _link(m: re.Match[str]) -> str:
        label = _render_inline(m.group("label"))
        href = m.group("href").strip()
        title = (m.group("title") or "").strip().strip('"')
        # URL scheme allowlist (defence against javascript:/data:/vbscript: XSS).
        safe_href = _safe_url(href)
        if safe_href is None:
            # Disallowed scheme: render label as plain text (no anchor).
            return f'<span class="okf-link-blocked" title="blocked: { _escape_attr(href) }">{label}</span>'
        attrs = f' href="{_escape_attr(safe_href)}"'
        if title:
            attrs += f' title="{_escape_attr(title)}"'
        # Auto-mark internal vs external (server/render rewrites href later).
        if _looks_internal(safe_href):
            attrs += ' class="okf-internal"'
        else:
            attrs += ' class="okf-external" rel="noopener noreferrer" target="_blank"'
        return f"<a{attrs}>{label}</a>"

    text = re.sub(
        r"\[(?P<label>[^\]]*)\]\((?P<href>[^)\s]+)(?:\s+\"(?P<title>[^\"]*)\")?\)",
        _link,
        text,
    )

    # Emphasis / strong.
    for pat, repl in _EMPH_RES:
        text = pat.sub(repl, text)

    # Images: ![alt](src) — emit after link substitution so the link regex
    # does not eat them. We re-scan raw text here. Apply the same URL
    # scheme allowlist to image sources.
    text = re.sub(
        r'!<img[^>]*alt="([^"]*)"[^>]*src="([^"]+)"[^>]*>',
        lambda m: _img_tag(m.group(1), m.group(2)),
        text,
    )
    text = re.sub(
        r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)\)",
        lambda m: _img_tag(m.group("alt"), m.group("src")),
        text,
    )

    # Restore stashed inline code.
    for i in range(len(stash)):
        text = text.replace(f"\x01{i}\x01", stash[i])
    return text


# ---------------------------------------------------------------------------
# URL safety
# ---------------------------------------------------------------------------

# Allowed URL schemes for href/src attributes. Anything else is neutralised.
# This list is the OWASP "safe URL" subset for links/images in user content.
_ALLOWED_URL_SCHEMES: frozenset[str] = frozenset({
    "http", "https", "mailto", "tel", "ftp",
})

_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):")


def _safe_url(href: str) -> str | None:
    """Return a safe-to-emit href, or None if the scheme is disallowed.

    Allowed:
        - Explicit schemes in ``_ALLOWED_URL_SCHEMES``.
        - Anchor-only links (``#section``).
        - Site-relative absolute paths (``/foo``).
        - Relative paths (``./foo``, ``../foo``, ``foo.md``).

    Disallowed (returns None):
        - ``javascript:``, ``data:``, ``vbscript:``, ``file:``, and any
          other scheme not in the allowlist. These would allow XSS when
          rendered into an ``<a href>`` or ``<img src>`` attribute.
        - URLs containing ASCII control characters (TAB, LF, CR, NUL, etc.)
          which browsers strip before scheme resolution and could be used
          to smuggle ``javascript:`` past the scheme check.
    """
    if not href:
        return None
    # Strip leading/trailing whitespace (browsers do this before resolution).
    href = href.strip()
    if not href:
        return None
    # Reject any ASCII control characters (0x00-0x20, 0x7f) which browsers
    # strip from URLs before scheme resolution. Without this, an href like
    # "java\tscript:alert(1)" passes the scheme regex (the tab breaks the
    # match) but the browser resolves it to "javascript:alert(1)".
    if any(ord(c) <= 0x20 or ord(c) == 0x7f for c in href):
        return None
    # Anchor-only.
    if href.startswith("#"):
        return href
    # Absolute site path.
    if href.startswith("/"):
        # Reject "//host" protocol-relative URLs (could be confused with a
        # scheme; browsers treat them as same-protocol).
        if href.startswith("//"):
            return None
        return href
    # Relative path.
    if href.startswith("./") or href.startswith("../"):
        return href
    # Bare relative (e.g. "foo.md", "foo/bar.md"). Treat as relative iff
    # there is no scheme before any path separator.
    m = _SCHEME_RE.match(href)
    if m:
        scheme = m.group(1).lower()
        if scheme in _ALLOWED_URL_SCHEMES:
            return href
        return None
    # No scheme detected and does not start with `/`, `./`, `../`, `#`:
    # treat as relative (e.g. "foo.md", "image.png"). This is the
    # conventional markdown case for sibling files.
    return href


def _img_tag(alt: str, src: str) -> str:
    safe_src = _safe_url(src)
    if safe_src is None:
        return (
            f'<span class="okf-img-blocked" title="blocked: '
            f'{_escape_attr(src)}">{_escape(alt)}</span>'
        )
    return (
        f'<img alt="{_escape_attr(alt)}" src="{_escape_attr(safe_src)}" '
        f'loading="lazy" />'
    )


def _looks_internal(href: str) -> bool:
    if not href:
        return False
    if href.startswith("#"):
        return False  # anchor; left as-is
    if "://" in href:
        return False
    if href.startswith("mailto:") or href.startswith("tel:"):
        return False
    return href.endswith(".md") or href.startswith("/") or href.startswith("./") or href.startswith("../")


# ---------------------------------------------------------------------------
# Escaping
# ---------------------------------------------------------------------------

def _escape(s: str, *, escape_quotes: bool = False) -> str:
    s = (s.replace("&", "&amp;")
          .replace("<", "&lt;")
          .replace(">", "&gt;"))
    if escape_quotes:
        s = s.replace('"', "&quot;")
    return s


def _escape_attr(s: str) -> str:
    return _escape(s, escape_quotes=True)


# ---------------------------------------------------------------------------
# Block renderer
# ---------------------------------------------------------------------------

def _render_fenced(code: str, lang: str, indent: str) -> str:
    lang_clean = lang.strip().lower()
    # Mermaid diagrams: render as <div class="mermaid"> so the CDN-loaded
    # mermaid.js can pick them up. Degrades to the code block text if the
    # CDN is unreachable (the div still shows the source, just unstyled).
    if lang_clean == "mermaid":
        return f'<div class="mermaid">{_escape(code)}</div>'
    # Math (KaTeX-style): mark for client-side rendering. Degrades to
    # the raw LaTeX if KaTeX isn't loaded.
    if lang_clean in ("math", "katex", "latex"):
        return f'<div class="math">{_escape(code)}</div>'
    cls = f' class="language-{_escape_attr(lang.strip())}"' if lang.strip() else ""
    return f"<pre><code{cls}>{_escape(code)}</code></pre>"


def _render_table(header: str, rows: list[str]) -> str:
    def _row(line: str, tag: str) -> str:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rendered = "".join(f"<{tag}>{_render_inline(c)}</{tag}>" for c in cells)
        return f"<tr>{rendered}</tr>"

    out = ['<table class="okf-table">']
    if header:
        out.append("<thead>")
        out.append(_row(header, "th"))
        out.append("</thead>")
    out.append("<tbody>")
    for r in rows:
        out.append(_row(r, "td"))
    out.append("</tbody>")
    out.append("</table>")
    return "\n".join(out)


_LIST_ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*+]|\d+\.)\s+(?P<text>.*)$")


def _render_list_block(lines: list[str]) -> str:
    """Render a contiguous run of list-item lines as a nested list."""
    # Each item: (indent_depth, ordered, text, children_lines)
    root_items: list[dict] = []
    stack: list[dict] = []  # each dict: {ordered, items: [...]}

    def _depth(line: str) -> int:
        m = _LIST_ITEM_RE.match(line)
        return len(m.group("indent").expandtabs(4)) if m else 0

    for line in lines:
        m = _LIST_ITEM_RE.match(line)
        if not m:
            continue
        depth = _depth(line)
        ordered = not m.group("marker") in "-*+"
        node = {"ordered": ordered, "text": m.group("text"), "children": []}

        # Pop stack while top has >= depth.
        while stack and stack[-1]["depth"] >= depth:
            stack.pop()

        if not stack:
            root_items.append(node)
        else:
            stack[-1]["node"]["children"].append(node)
        stack.append({"depth": depth, "node": node})

    # P2-15 (SEC-005 / §13.x DoS): cap _emit recursion at 32 levels to
    # match the blockquote cap. A 1000-deep nested list (≈30KB) would
    # otherwise blow Python's default 1000-frame recursion limit and
    # crash /__preview / build / render. Deeper nests flatten to inline
    # text rather than nesting further (no information loss for legit
    # content; legit lists rarely exceed 6-7 levels).
    _MAX_LIST_NESTING = 32

    def _emit(node: dict, _d: int = 0) -> str:
        tag = "ol" if node["ordered"] else "ul"
        body = f"<li>{_render_inline(node['text'])}"
        if node["children"] and _d < _MAX_LIST_NESTING:
            child_items = "".join(_emit(c, _d + 1) for c in node["children"])
            body += f"\n<{tag}>{child_items}</{tag}>"
        elif node["children"]:
            # At the cap: flatten remaining children as inline text so the
            # content is still readable without recursing further.
            flat = "; ".join(
                _render_inline(child["text"])
                for child in _iter_all_children(node)
            )
            body += f" ({flat})"
        body += "</li>"
        return body

    def _iter_all_children(node: dict) -> Iterator[dict]:
        """Yield every descendant of ``node`` in document order (BFS)."""
        queue = list(node["children"])
        while queue:
            n = queue.pop(0)
            yield n
            queue.extend(n["children"])

    if not root_items:
        return ""
    # Group consecutive root items by their `ordered` flag so adjacent
    # unordered + ordered lists become separate <ul>/<ol> elements.
    out_parts: list[str] = []
    current_tag = "ol" if root_items[0]["ordered"] else "ul"
    current_items: list[str] = []
    for node in root_items:
        tag = "ol" if node["ordered"] else "ul"
        if tag != current_tag:
            out_parts.append(f"<{current_tag}>{''.join(current_items)}</{current_tag}>")
            current_items = []
            current_tag = tag
        current_items.append(_emit(node))
    out_parts.append(f"<{current_tag}>{''.join(current_items)}</{current_tag}>")
    return "\n".join(out_parts)


def _split_blocks(text: str) -> list[tuple[str, str]]:
    """Split into (kind, payload) blocks.

    Kinds: 'fence', 'heading', 'hr', 'table', 'list', 'quote', 'blank',
    'para'. Fenced blocks are extracted first (so their bodies don't get
    mis-parsed), then the remaining text is scanned line-by-line.
    """
    blocks: list[tuple[str, str]] = []
    # Carve out fenced code blocks first.
    fence_spans: list[tuple[int, int]] = []
    cleaned = text

    def _carve(m: re.Match[str]) -> str:
        fence_spans.append((m.start(), m.end()))
        # Replace with a placeholder line of equal length so other regexes'
        # offsets remain valid. Use a comment-style sentinel.
        return f"\x02FENCE{len(blocks)}\x02" + ("\n" * (m.group(0).count("\n")))

    # Iterate fence matches and collect blocks.
    fence_matches = list(_FENCE_RE.finditer(text))
    placeholders: list[str] = []
    fence_block_meta: list[tuple[str, str]] = []
    cursor = 0
    cleaned_parts: list[str] = []
    for m in fence_matches:
        cleaned_parts.append(text[cursor:m.start()])
        idx = len(fence_block_meta)
        fence_block_meta.append((m.group("code"), m.group("lang"), m.group("indent")))
        cleaned_parts.append(f"\x02FENCE{idx}\x02")
        cursor = m.end()
    cleaned_parts.append(text[cursor:])
    cleaned = "".join(cleaned_parts)

    # Now scan cleaned line-by-line for the other block kinds.
    lines = cleaned.split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Fence placeholder?
        m_fence = re.match(r"^\x02FENCE(\d+)\x02\s*$", stripped)
        if m_fence:
            idx = int(m_fence.group(1))
            code, lang, indent = fence_block_meta[idx]
            blocks.append(("fence", f"{code}\x03{lang}\x03{indent}"))
            i += 1
            continue

        if not stripped:
            i += 1
            continue

        # Heading
        m_h = re.match(r"^(#{1,6})\s+(.*?)(?:\s+#+)?$", stripped)
        if m_h:
            level = len(m_h.group(1))
            text_h = m_h.group(2)
            blocks.append(("heading", f"{level}\x03{text_h}"))
            i += 1
            continue

        # Horizontal rule
        if _HR_RE.match(stripped):
            blocks.append(("hr", ""))
            i += 1
            continue

        # Table: a line with '|' followed by a separator line.
        if "|" in stripped and i + 1 < n and _TABLE_SEP_RE.match(lines[i + 1].strip()):
            header = stripped
            j = i + 2
            rows: list[str] = []
            while j < n and lines[j].strip() and "|" in lines[j]:
                rows.append(lines[j].strip())
                j += 1
            blocks.append(("table", f"{header}\x04" + "\x04".join(rows)))
            i = j
            continue

        # Blockquote: collect consecutive lines starting with '>'
        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while i < n and lines[i].lstrip().startswith(">"):
                # Strip a single leading '>' and one optional space.
                qline = re.sub(r"^\s*>\s?", "", lines[i])
                quote_lines.append(qline)
                i += 1
            blocks.append(("quote", "\n".join(quote_lines)))
            continue

        # List: collect consecutive list-item lines (and their continuation)
        if _LIST_ITEM_RE.match(line):
            list_lines: list[str] = []
            while i < n:
                cur = lines[i]
                if _LIST_ITEM_RE.match(cur) or (cur.strip() == "" and i + 1 < n and _LIST_ITEM_RE.match(lines[i + 1])):
                    if cur.strip() == "":
                        # blank line inside a list (loose list) — keep going only if next is still indented/item
                        if i + 1 < n and (_LIST_ITEM_RE.match(lines[i + 1]) or lines[i + 1].startswith("  ")):
                            list_lines.append(cur)
                            i += 1
                            continue
                        else:
                            break
                    list_lines.append(cur)
                    i += 1
                elif cur.startswith("  ") and list_lines:
                    # Continuation of previous item (indented).
                    list_lines[-1] += " " + cur.strip()
                    i += 1
                else:
                    break
            blocks.append(("list", "\n".join(list_lines)))
            continue

        # Otherwise, gather a paragraph until a blank line or block-starting line.
        para: list[str] = []
        while i < n:
            cur = lines[i]
            cur_stripped = cur.strip()
            if not cur_stripped:
                break
            if re.match(r"^\x02FENCE\d+\x02", cur_stripped):
                break
            if re.match(r"^#{1,6}\s+", cur_stripped):
                break
            if _HR_RE.match(cur_stripped):
                break
            if cur_stripped.startswith(">"):
                break
            if _LIST_ITEM_RE.match(cur):
                break
            if "|" in cur_stripped and i + 1 < n and _TABLE_SEP_RE.match(lines[i + 1].strip()):
                break
            para.append(cur_stripped)
            i += 1
        if para:
            blocks.append(("para", " ".join(para)))

    return blocks


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def markdown_to_html(text: str, *, _depth: int = 0) -> str:
    """Render the OKF markdown subset to HTML.

    Pure text→HTML. Links are emitted verbatim and tagged with
    ``class="okf-internal"`` / ``class="okf-external"`` for downstream
    rewriting via :func:`rewrite_internal_links`.

    P1-1 (iter-4): blockquote rendering recurses via ``markdown_to_html``;
    a deeply nested ``> > > > …`` body (~1000 levels, 3KB) triggers
    ``RecursionError`` and crashes ``okf build``/``render`` + the
    ``/__data/graph.json`` bulk endpoint. Cap recursion at 32 levels
    (well beyond any legitimate nesting); deeper quotes are escaped
    as plain text.
    """
    if not text:
        return ""
    # Normalize CRLF.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = _split_blocks(text)

    out: list[str] = []
    # Slug counters for duplicate headings.
    seen_slugs: dict[str, int] = {}

    for kind, payload in blocks:
        if kind == "fence":
            code, lang, indent = payload.split("\x03")
            out.append(_render_fenced(code, lang, indent))
        elif kind == "heading":
            level_str, htext = payload.split("\x03", 1)
            level = int(level_str)
            slug = _slugify(htext)
            if slug in seen_slugs:
                seen_slugs[slug] += 1
                slug = f"{slug}-{seen_slugs[slug]}"
            else:
                seen_slugs[slug] = 0
            out.append(
                f'<h{level} id="{_escape_attr(slug)}">{_render_inline(htext)}</h{level}>'
            )
        elif kind == "hr":
            out.append("<hr />")
        elif kind == "table":
            parts = payload.split("\x04")
            header = parts[0]
            rows = [p for p in parts[1:] if p]
            out.append(_render_table(header, rows))
        elif kind == "quote":
            if _depth >= 32:
                # P1-1: recursion cap — escape deeply nested quotes as text.
                out.append(f"<blockquote>{_escape(payload)}</blockquote>")
            else:
                inner = markdown_to_html(payload, _depth=_depth + 1)
                out.append(f"<blockquote>{inner}</blockquote>")
        elif kind == "list":
            out.append(_render_list_block(payload.split("\n")))
        elif kind == "para":
            out.append(f"<p>{_render_inline(payload)}</p>")

    return "\n".join(out)


def rewrite_internal_links(
    html: str, link_map: Mapping[str, str | None]
) -> str:
    """Rewrite internal ``<a href>`` URLs using a target_raw → url map.

    ``link_map`` maps each ``target_raw`` (the exact link as written in
    markdown, e.g. ``/a/b.md`` or ``./c.md``) to its viewer URL (or ``None``
    if the link is unresolved/broken — the href is left intact and a
    ``data-okf-broken`` attribute is added).

    Anchor-only and external links are passed through untouched. The
    markdown renderer already added ``class="okf-internal"`` to candidate
    internal links, but this function decides the final href purely from
    ``link_map``.
    """
    def _replace(m: re.Match[str]) -> str:
        pre = m.group(1)
        quote = m.group(2)
        href = m.group("href")
        # Strip an optional anchor for lookup.
        anchor = ""
        lookup = href
        if "#" in href:
            lookup, anchor = href.split("#", 1)
            anchor = f"#{anchor}"
        if lookup in link_map:
            url = link_map[lookup]
            if url is None:
                # Unresolved internal link — flag it but keep href readable.
                return f'{pre}href={quote}{href}{quote} data-okf-broken="1"'
            new_href = url + anchor
            return f'{pre}href={quote}{new_href}{quote}'
        return m.group(0)

    return _LINK_HREF_RE.sub(_replace, html)


# ---------------------------------------------------------------------------
# URL helpers (per build mode)
# ---------------------------------------------------------------------------

def url_for_concept(
    cid: ConceptId,
    mode: str,
    *,
    source_cid: ConceptId | None = None,
) -> str:
    """Return the URL for a concept under the given build mode.

    Modes:
        serve, spa → ``/<concept_id>`` (absolute, no extension)
        static     → relative path from ``source_cid``'s file to the target's
                     ``.html`` file (so the site works without a server)
    """
    cid_str = concept_id_to_str(cid)
    if mode in ("serve", "spa"):
        return "/" + cid_str
    # static
    target_rel = "/".join(cid[:-1] + (cid[-1] + ".html",))
    if source_cid is None or len(source_cid) <= 1:
        return target_rel
    source_dir = "/".join(source_cid[:-1])
    return posixpath.relpath(target_rel, source_dir) if source_dir else target_rel
