"""
extract.py — turn a rendered page's HTML into clean, comparable text for one watch.

Who uses it: checker.py (every check), routes/picker.py (the "Test selection" preview), noise learning.
Depends on: BeautifulSoup + lxml (fast HTML parsing; soupsieve gives us CSS selectors), noise.py.

Steps (requirement 3):
1. Remove things that are never content: scripts, styles, iframes, SVGs, comments, hidden elements.
2. Remove noise: built-in selectors (cookie banners, ads, chat widgets, carousels) + the user's ignore
   regions + learned volatile element rules.
3. If the user picked watch regions, keep only those elements (in page order, a blank line between them).
   Otherwise keep the whole <body>.
4. Turn block elements (p, div, li, h1...) into line breaks, collapse spaces, drop empty lines.
"""
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from . import noise

STRIP_TAGS = ["script", "style", "noscript", "iframe", "svg", "canvas", "video", "audio", "template", "object", "embed"]
HIDDEN_SELECTORS = ["[hidden]", '[aria-hidden="true"]', '[style*="display:none" i]', '[style*="display: none" i]',
                    '[style*="visibility:hidden" i]', '[style*="visibility: hidden" i]']
BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt", "fieldset", "figcaption", "figure",
    "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre",
    "section", "table", "tbody", "thead", "tfoot", "tr", "ul", "td", "th", "caption", "summary", "details", "option",
    "label", "button", "legend",
}
CELL_TAGS = {"td", "th"}
SPACES = re.compile(r"[ \t\r\f\v ​]+")


@dataclass
class Extracted:
    text: str
    title: str
    missing_selectors: list[str] = field(default_factory=list)
    invalid_selectors: list[str] = field(default_factory=list)


def parse(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "lxml")


def _safe_select(root: Tag | BeautifulSoup, selector: str) -> list[Tag] | None:
    """soup.select() that returns None (instead of crashing) for a selector the parser doesn't support."""
    try:
        return root.select(selector)
    except Exception:  # soupsieve raises several error types for bad selectors
        return None


def remove_noise(soup: BeautifulSoup, ignore_selectors: list[str], ignore_carousels: bool,
                 volatile_selectors: list[str] | None = None) -> list[str]:
    """Delete non-content and noise elements from the soup in place. Returns invalid user selectors."""
    for tag in soup(STRIP_TAGS):
        tag.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    invalid: list[str] = []
    # Learned volatile-element rules first: they were learned on a DOM with only scripts/comments removed
    # (see learn_rules in checker.py), so their :nth-of-type positions match only at this stage.
    for sel in list(volatile_selectors or []) + HIDDEN_SELECTORS + noise.builtin_selectors(ignore_carousels):
        for el in _safe_select(soup, sel) or []:
            if el.name not in ("html", "body"):
                el.decompose()
    for sel in ignore_selectors:
        found = _safe_select(soup, sel)
        if found is None:
            invalid.append(sel)
            continue
        for el in found:
            el.decompose()
    return invalid


def element_text(el: Tag) -> str:
    """Text of one element with block elements turned into line breaks. Keeps <img alt> text."""
    parts: list[str] = []

    def walk(node) -> None:
        if isinstance(node, Comment):
            return
        if isinstance(node, NavigableString):
            parts.append(str(node))
            return
        if not isinstance(node, Tag):
            return
        if node.name == "img":
            alt = (node.get("alt") or "").strip()
            if alt:
                parts.append(f" {alt} ")
            return
        if node.name == "br":
            parts.append("\n")
            return
        block = node.name in BLOCK_TAGS
        if block:
            parts.append("\n")
        for child in node.children:
            walk(child)
        if node.name in CELL_TAGS:
            parts.append(" \t ")
        elif block:
            parts.append("\n")

    walk(el)
    return clean_text("".join(parts))


def clean_text(text: str) -> str:
    """Collapse runs of spaces, trim each line, drop empty lines."""
    lines = []
    for line in text.split("\n"):
        line = SPACES.sub(" ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _drop_nested(elements: list[Tag]) -> list[Tag]:
    """If both a parent and its child were selected, keep only the parent (avoid duplicate text)."""
    chosen = set(id(e) for e in elements)
    out = []
    for el in elements:
        if any(id(parent) in chosen for parent in el.parents):
            continue
        out.append(el)
    return out


def extract(html: str, watch_selectors: list[str], ignore_selectors: list[str], ignore_carousels: bool = True,
            volatile_selectors: list[str] | None = None) -> Extracted:
    """Full pipeline for one watch on one fetched HTML document."""
    soup = parse(html)
    title = soup.title.get_text(strip=True) if soup.title else ""
    invalid = remove_noise(soup, ignore_selectors, ignore_carousels, volatile_selectors)

    if not watch_selectors:
        root = soup.body or soup
        return Extracted(element_text(root), title, [], invalid)

    picked: list[Tag] = []
    missing: list[str] = []
    for sel in watch_selectors:
        found = _safe_select(soup, sel)
        if found is None:
            invalid.append(sel)
            missing.append(sel)
        elif not found:
            missing.append(sel)
        else:
            picked.extend(found)
    # Document order: sort by position in the original HTML.
    order = {id(el): i for i, el in enumerate(soup.find_all(True))}
    picked = _drop_nested(sorted({id(e): e for e in picked}.values(), key=lambda e: order.get(id(e), 0)))
    blocks = [element_text(el) for el in picked]
    text = "\n\n".join(b for b in blocks if b)
    return Extracted(text, title, missing, invalid)


def page_title(html: str) -> str:
    soup = parse(html)
    return soup.title.get_text(strip=True)[:120] if soup.title else ""


def visible_text_of_raw_html(html: str) -> str:
    """Quick text of the server-sent HTML (no JavaScript). Used to decide if a page is static."""
    soup = parse(html)
    for tag in soup(STRIP_TAGS):
        tag.decompose()
    return element_text(soup.body or soup)


# ---------------------------------------------------------------------------
# Finding the element behind a volatile line (for learned selector rules).
# ---------------------------------------------------------------------------

STABLE_CLASS = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{1,30}$")
RANDOM_LOOKING = re.compile(r"(?:^css-|^sc-|^jsx-|^_|[0-9a-f]{6,}|\d{3,})")


def _stable_classes(el: Tag) -> list[str]:
    return [c for c in (el.get("class") or []) if STABLE_CLASS.match(c) and not RANDOM_LOOKING.search(c)][:2]


def css_path(el: Tag) -> str | None:
    """A CSS selector path for an element, built from stable ids/classes and :nth-of-type.

    Same idea as picker.js (the browser-side picker), in Python: prefer a stable id, otherwise
    tag.class steps upward until the body, max depth 6.
    """
    parts: list[str] = []
    node: Tag | None = el
    depth = 0
    while node is not None and node.name not in ("html", "body", "[document]") and depth < 6:
        node_id = node.get("id")
        if node_id and STABLE_CLASS.match(node_id) and not RANDOM_LOOKING.search(node_id):
            parts.append(f"#{node_id}")
            break
        step = node.name
        classes = _stable_classes(node)
        if classes:
            step += "".join(f".{c}" for c in classes)
        parent = node.parent
        if isinstance(parent, Tag):
            same = [s for s in parent.find_all(node.name, recursive=False)]
            if len(same) > 1:
                step += f":nth-of-type({same.index(node) + 1})"
        parts.append(step)
        node = parent if isinstance(parent, Tag) else None
        depth += 1
    if not parts:
        return None
    return " > ".join(reversed(parts))


def learning_soup(html: str) -> BeautifulSoup:
    """The DOM that volatile selector rules are learned on: only scripts/styles/comments removed."""
    soup = parse(html)
    for tag in soup(STRIP_TAGS):
        tag.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    return soup


def element_for_line(soup: BeautifulSoup, raw_line: str) -> Tag | None:
    """The smallest block element whose text contains this line (for volatile selector learning)."""
    needle = SPACES.sub(" ", raw_line).strip()
    if len(needle) < 3:
        return None
    probe = needle[:40]
    for text_node in soup.find_all(string=True):
        if isinstance(text_node, Comment):
            continue
        if probe[:20] and probe[:20] in SPACES.sub(" ", str(text_node)):
            el = text_node.parent
            while isinstance(el, Tag) and el.name not in BLOCK_TAGS and el.parent is not None:
                el = el.parent
            if isinstance(el, Tag) and el.name not in ("html", "body", "main"):
                if needle[:60] in SPACES.sub(" ", el.get_text(" ")):
                    return el
    return None
