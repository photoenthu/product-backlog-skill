#!/usr/bin/env python3
"""Pure-stdlib Markdown -> HTML renderer for the new-product-backlog editor.

This is a *read-only viewer*: it turns a Markdown document (plans, specs, notes)
into a safe, self-contained HTML page served from the editor's own origin. It is
NOT a full CommonMark implementation -- it supports a pragmatic subset chosen to
make plans and specs readable.

SECURITY MODEL
--------------
The output is served as ``text/html`` from the editor's origin, so it must never
carry live script. Every piece of literal document text is passed through
``html.escape`` before any tag is emitted, and the renderer only ever produces a
fixed, hand-built tag set (h1-h6, p, strong, em, code, pre, ul/ol/li,
blockquote, hr, a, table/thead/tbody/tr/th/td, br). Any raw HTML that appears in
the Markdown source therefore shows up as escaped, visible text -- e.g.
``<script>alert(1)</script>`` renders as the literal characters, never a tag.

Link hrefs are sanitized by :func:`safe_href`: only http/https, in-page anchors,
and scheme-less relative paths (rewritten to route through the editor's ``/file``
endpoint) become real ``<a>`` links. Every other scheme (javascript:, data:,
vbscript:, mailto:, file:, ...) is refused and the link text is rendered as
plain escaped text.

Public API:
    to_fragment(md_text, link_base="")            -> safe HTML fragment
    render_page(md_text, title, link_base="")     -> full self-contained document
"""
from __future__ import annotations

import html
import posixpath
import re
import urllib.parse

# A private-use-area sentinel used to protect already-rendered inline spans
# (code, links) from later inline passes and from html.escape. Constructed via
# chr() so no control byte ever appears in this source file. It is always fully
# substituted back out before a fragment is returned, so it never reaches output.
_MARK = chr(0xE000)

# Chars a browser would ignore inside a URL and that could otherwise hide a
# scheme (e.g. "java\tscript:"). Stripped before probing for a scheme. Mirrors
# the editor's safeArtifactUrl.
_URL_JUNK = re.compile(r"[\x00-\x20\x7f-\x9f]")
_SCHEME = re.compile(r"^([a-z][a-z0-9+.-]*):")

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_HR = re.compile(r"^\s*([-*_])\s*(?:\1\s*){2,}$")
_LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$")


# --------------------------------------------------------------------------- #
# Link sanitization
# --------------------------------------------------------------------------- #
def safe_href(url: str, link_base: str = ""):
    """Sanitize a Markdown link/image URL.

    Returns ``(href, kind)`` where ``kind`` is one of ``"external"``,
    ``"anchor"``, ``"relative"``, or ``None`` (meaning: not a permissible link,
    render its text as plain escaped text). ``href`` is ``None`` when ``kind`` is
    ``None``.
    """
    s = (url or "").strip()
    if not s:
        return None, None
    probe = _URL_JUNK.sub("", s).lower()
    m = _SCHEME.match(probe)
    if m:
        # Has an explicit scheme: only http/https are allowed.
        if m.group(1) in ("http", "https"):
            return s, "external"
        return None, None
    if probe.startswith("#"):
        # In-page anchor: keep as-is, stays in the same document.
        return s, "anchor"
    # Scheme-less relative path: resolve against the document's directory and
    # route through the editor's /file endpoint so cross-doc links open in the
    # viewer too. Drop any #fragment for the /file lookup.
    frag = s.split("#", 1)[0]
    if frag.startswith("/"):
        joined = posixpath.normpath(frag)
    else:
        joined = posixpath.normpath(posixpath.join(link_base or "", frag))
    joined = joined.lstrip("/")
    href = "/file?path=" + urllib.parse.quote(joined, safe="/")
    return href, "relative"


def _anchor(url: str, label: str, link_base: str) -> str:
    """Render a link or image label as a sanitized ``<a>`` (or plain escaped
    text when the URL is not a permissible link)."""
    href, kind = safe_href(url, link_base)
    text = html.escape(label) if label else html.escape(url.strip())
    if not text:
        text = html.escape(url.strip())
    if kind is None:
        return text
    attrs = 'href="' + html.escape(href, quote=True) + '"'
    if kind in ("external", "relative"):
        attrs += ' target="_blank" rel="noopener noreferrer"'
    return "<a " + attrs + ">" + text + "</a>"


# --------------------------------------------------------------------------- #
# Inline formatting
# --------------------------------------------------------------------------- #
_CODE_SPAN = re.compile(r"`([^`]+)`")
# The URL part allows one level of balanced parens -- so a URL like
# `javascript:alert(1)` or `https://e.com/a_(b)` is captured whole rather than
# leaving a stray ")" behind -- plus an optional "title" which is ignored.
_URL_PART = r'((?:[^()\s]|\([^()\s]*\))*)(?:\s+"[^"]*")?'
_IMAGE = re.compile(r"!\[([^\]]*)\]\(\s*" + _URL_PART + r"\s*\)")
_LINK = re.compile(r"\[([^\]]*)\]\(\s*" + _URL_PART + r"\s*\)")
_BOLD_STAR = re.compile(r"\*\*(.+?)\*\*")
_BOLD_USCORE = re.compile(r"__(.+?)__")
_ITALIC_STAR = re.compile(r"\*(?=\S)(.+?)(?<=\S)\*")
_ITALIC_USCORE = re.compile(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)")


def render_inline(text: str, link_base: str = "") -> str:
    """Render inline Markdown in a run of text to safe HTML.

    Code spans and links/images are extracted first (protected behind sentinels)
    so their contents are not double-transformed; the remaining text is then
    escaped and emphasis is applied."""
    stash: list[str] = []

    def keep(frag: str) -> str:
        stash.append(frag)
        return _MARK + str(len(stash) - 1) + _MARK

    # 1. Code spans -- escaped, no further inline inside.
    text = _CODE_SPAN.sub(
        lambda m: keep("<code>" + html.escape(m.group(1)) + "</code>"), text
    )
    # 2. Images -> sanitized link labeled with the alt text (never <img>).
    text = _IMAGE.sub(
        lambda m: keep(_anchor(m.group(2), m.group(1), link_base)), text
    )
    # 3. Links -> sanitized <a> (or plain escaped text).
    text = _LINK.sub(
        lambda m: keep(_anchor(m.group(2), m.group(1), link_base)), text
    )
    # 4. Escape everything that is left (literal document text).
    text = html.escape(text)
    # 5. Emphasis -- bold before italic so ** / __ win over * / _.
    text = _BOLD_STAR.sub(r"<strong>\1</strong>", text)
    text = _BOLD_USCORE.sub(r"<strong>\1</strong>", text)
    text = _ITALIC_STAR.sub(r"<em>\1</em>", text)
    text = _ITALIC_USCORE.sub(r"<em>\1</em>", text)
    # 6. Restore protected spans.
    for i, frag in enumerate(stash):
        text = text.replace(_MARK + str(i) + _MARK, frag)
    return text


# --------------------------------------------------------------------------- #
# Block parsing
# --------------------------------------------------------------------------- #
def _split_table_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _table_alignments(sep_line: str) -> list[str]:
    aligns = []
    for cell in _split_table_row(sep_line):
        c = cell.strip()
        left = c.startswith(":")
        right = c.endswith(":")
        if left and right:
            aligns.append("center")
        elif right:
            aligns.append("right")
        elif left:
            aligns.append("left")
        else:
            aligns.append("")
    return aligns


def _render_table(header: str, sep: str, body: list[str], link_base: str) -> str:
    aligns = _table_alignments(sep)
    heads = _split_table_row(header)

    def cell(tag: str, content: str, idx: int) -> str:
        a = aligns[idx] if idx < len(aligns) else ""
        style = ' style="text-align:' + a + '"' if a else ""
        return "<" + tag + style + ">" + render_inline(content, link_base) + "</" + tag + ">"

    out = ["<table>", "<thead>", "<tr>"]
    out += [cell("th", h, i) for i, h in enumerate(heads)]
    out += ["</tr>", "</thead>", "<tbody>"]
    for row in body:
        cells = _split_table_row(row)
        out.append("<tr>")
        out += [cell("td", c, i) for i, c in enumerate(cells)]
        out.append("</tr>")
    out += ["</tbody>", "</table>"]
    return "".join(out)


def _render_list(entries: list[tuple[int, bool, str]], pos: int, indent: int,
                 link_base: str):
    """Build a (possibly nested) list from `entries` starting at `pos`, for the
    given indentation level. Returns (html, next_pos)."""
    ordered = entries[pos][1]
    tag = "ol" if ordered else "ul"
    parts = ["<" + tag + ">"]
    while pos < len(entries):
        e_indent, e_ordered, e_text = entries[pos]
        if e_indent < indent:
            break
        if e_indent > indent:
            # Deeper item: nest it inside the previous <li>.
            nested, pos = _render_list(entries, pos, e_indent, link_base)
            if len(parts) > 1 and parts[-1].endswith("</li>"):
                parts[-1] = parts[-1][: -len("</li>")] + nested + "</li>"
            else:
                parts.append("<li>" + nested + "</li>")
            continue
        parts.append("<li>" + render_inline(e_text, link_base) + "</li>")
        pos += 1
    parts.append("</" + tag + ">")
    return "".join(parts), pos


def to_fragment(md_text: str, link_base: str = "") -> str:
    """Convert a Markdown document body to a safe HTML fragment."""
    text = (md_text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    n = len(lines)
    out: list[str] = []
    i = 0
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Blank line -> block separator.
        if not stripped:
            i += 1
            continue

        # Fenced code block.
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            i += 1
            code: list[str] = []
            while i < n and lines[i].strip()[:3] != fence:
                code.append(lines[i])
                i += 1
            if i < n:  # consume the closing fence
                i += 1
            out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
            continue

        # Horizontal rule.
        if _HR.match(line):
            out.append("<hr>")
            i += 1
            continue

        # ATX heading.
        m = _HEADING.match(line)
        if m:
            level = len(m.group(1))
            out.append("<h{0}>{1}</h{0}>".format(level, render_inline(m.group(2), link_base)))
            i += 1
            continue

        # Pipe table: header row followed by a separator row.
        if "|" in line and i + 1 < n and _TABLE_SEP.match(lines[i + 1]) and "|" in lines[i + 1]:
            header = line
            sep = lines[i + 1]
            i += 2
            body: list[str] = []
            while i < n and lines[i].strip() and "|" in lines[i]:
                body.append(lines[i])
                i += 1
            out.append(_render_table(header, sep, body, link_base))
            continue

        # Blockquote.
        if stripped.startswith(">"):
            quote: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner = render_inline(" ".join(q for q in quote if q.strip()), link_base)
            out.append("<blockquote>" + inner + "</blockquote>")
            continue

        # List (ordered or unordered), possibly nested.
        if _LIST_ITEM.match(line):
            entries: list[tuple[int, bool, str]] = []
            while i < n and _LIST_ITEM.match(lines[i]):
                lm = _LIST_ITEM.match(lines[i])
                indent = len(lm.group(1).replace("\t", "  "))
                ordered = lm.group(2)[0].isdigit()
                entries.append((indent, ordered, lm.group(3)))
                i += 1
            base_indent = min(e[0] for e in entries)
            html_list, _ = _render_list(entries, 0, base_indent, link_base)
            out.append(html_list)
            continue

        # Paragraph: gather consecutive lines until a blank line or a new block.
        para: list[str] = []
        while i < n:
            cur = lines[i]
            cs = cur.strip()
            if not cs:
                break
            if (cs.startswith("```") or cs.startswith("~~~") or _HR.match(cur)
                    or _HEADING.match(cur) or _LIST_ITEM.match(cur) or cs.startswith(">")):
                break
            if ("|" in cur and i + 1 < n and _TABLE_SEP.match(lines[i + 1])
                    and "|" in lines[i + 1]):
                break
            para.append(cs)
            i += 1
        if para:
            out.append("<p>" + render_inline(" ".join(para), link_base) + "</p>")

    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Full page
# --------------------------------------------------------------------------- #
_PAGE_CSS = """
:root {
  --bg: #ffffff; --fg: #1f2328; --muted: #57606a; --border: #d0d7de;
  --code-bg: #f6f8fa; --accent: #0969da; --quote-border: #d0d7de;
  --header-border: #d8dee4;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --border: #30363d;
    --code-bg: #161b22; --accent: #4493f8; --quote-border: #3d444d;
    --header-border: #21262d;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; padding: 2.5rem 1.25rem 5rem;
  background: var(--bg); color: var(--fg);
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}
main { max-width: 760px; margin: 0 auto; }
.doc-title {
  font-size: 0.8rem; letter-spacing: 0.04em; text-transform: uppercase;
  color: var(--muted); margin: 0 0 1.75rem; padding-bottom: 0.6rem;
  border-bottom: 1px solid var(--header-border); font-weight: 600;
}
h1, h2, h3, h4, h5, h6 { line-height: 1.3; margin: 1.8em 0 0.6em; font-weight: 600; }
h1 { font-size: 1.9rem; } h2 { font-size: 1.5rem; padding-bottom: 0.3rem; border-bottom: 1px solid var(--header-border); }
h3 { font-size: 1.25rem; } h4 { font-size: 1.05rem; } h5, h6 { font-size: 0.95rem; }
h1:first-child, h2:first-child, h3:first-child { margin-top: 0; }
p { margin: 0 0 1rem; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
strong { font-weight: 600; }
code {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 0.88em; background: var(--code-bg); padding: 0.15em 0.4em;
  border-radius: 6px; border: 1px solid var(--border);
}
pre {
  background: var(--code-bg); border: 1px solid var(--border); border-radius: 8px;
  padding: 1rem; overflow-x: auto; margin: 0 0 1rem;
}
pre code { background: none; border: 0; padding: 0; font-size: 0.85em; }
blockquote {
  margin: 0 0 1rem; padding: 0.2rem 1rem; color: var(--muted);
  border-left: 4px solid var(--quote-border);
}
ul, ol { margin: 0 0 1rem; padding-left: 1.6rem; }
li { margin: 0.2em 0; }
li > ul, li > ol { margin: 0.2em 0; }
hr { border: 0; border-top: 1px solid var(--border); margin: 2rem 0; }
table { border-collapse: collapse; margin: 0 0 1rem; display: block; overflow-x: auto; }
th, td { border: 1px solid var(--border); padding: 0.45rem 0.8rem; }
th { background: var(--code-bg); font-weight: 600; }
tbody tr:nth-child(2n) { background: var(--code-bg); }
"""


def render_page(md_text: str, title: str, link_base: str = "") -> str:
    """Return a complete, self-contained HTML document for `md_text`.

    No external resources: the stylesheet is inlined and the page is theme-aware
    via ``prefers-color-scheme``."""
    safe_title = html.escape(title or "Document")
    fragment = to_fragment(md_text, link_base)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>" + safe_title + "</title>\n"
        "<style>" + _PAGE_CSS + "</style>\n"
        "</head>\n<body>\n<main>\n"
        '<div class="doc-title">' + safe_title + "</div>\n"
        + fragment
        + "\n</main>\n</body>\n</html>\n"
    )
