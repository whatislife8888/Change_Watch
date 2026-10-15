"""
picker/frame.py — turns a stored page snapshot into a SAFE page for the visual picker (requirement 5).

Who uses it: routes/picker.py (GET /api/watches/{id}/picker/frame).
Depends on: BeautifulSoup.

We never show the live site. We show our stored copy of it, with everything that could run code removed:
  - every <script> (also inside SVG), every on* attribute (onclick, onload...), <meta http-equiv=refresh>,
    <object>, <embed>, <iframe>, <frame>, javascript: URLs; forms are disabled.
Then we add <base href="{page url}"> so the site's own CSS and images still load (the page looks right),
and inject our picker script inline with a random *nonce*. The Content-Security-Policy header only allows
scripts carrying that nonce — so even if the sanitiser missed something, the browser refuses to run it.
On top of that, the frontend embeds this in <iframe sandbox="allow-scripts"> without allow-same-origin.
Three independent layers of defence.
"""
import html as html_lib
import re
import secrets
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).parent
PICKER_JS = (HERE / "picker.js").read_text()
PICKER_CSS = (HERE / "picker.css").read_text()

DANGEROUS_TAGS = ["script", "object", "embed", "iframe", "frame", "frameset", "applet", "portal", "noscript"]
URL_ATTRS = ["href", "src", "action", "formaction", "xlink:href", "data", "poster", "background"]
JS_URL = re.compile(r"^\s*(javascript|vbscript|data:text/html)", re.IGNORECASE)


def build_csp(nonce: str) -> str:
    return (
        "default-src 'none'; "
        f"script-src 'nonce-{nonce}'; "
        "style-src * 'unsafe-inline'; "
        "img-src * data: blob:; "
        "font-src * data:; "
        "connect-src 'none'; frame-src 'none'; form-action 'none'; base-uri *"
    )


def sanitise(raw_html: str, base_url: str) -> tuple[str, str]:
    """Return (safe_html, nonce)."""
    soup = BeautifulSoup(raw_html or "", "lxml")
    for tag in soup.find_all(DANGEROUS_TAGS):
        tag.decompose()
    for meta in soup.find_all("meta"):
        if (meta.get("http-equiv") or "").lower() in ("refresh", "set-cookie", "content-security-policy"):
            meta.decompose()
    for base in soup.find_all("base"):
        base.decompose()
    for el in soup.find_all(True):
        for attr in list(el.attrs):
            name = attr.lower()
            if name.startswith("on") or name in ("srcdoc", "ping"):
                del el.attrs[attr]
            elif name in URL_ATTRS and isinstance(el.attrs[attr], str) and JS_URL.match(el.attrs[attr]):
                el.attrs[attr] = "#"
        if el.name == "form":
            el.attrs["action"] = "#"
        if el.name in ("input", "button", "select", "textarea"):
            el.attrs["disabled"] = "disabled"
    # <link rel=preload as=script>, import maps, etc. can't run without script-src, but drop them anyway.
    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel") or []).lower()
        if "import" in rel or "modulepreload" in rel or (rel == "preload" and link.get("as") == "script"):
            link.decompose()

    nonce = secrets.token_urlsafe(16)
    head = soup.head
    if head is None:
        head = soup.new_tag("head")
        (soup.html or soup).insert(0, head)
    base = soup.new_tag("base", href=base_url)
    head.insert(0, base)
    style = soup.new_tag("style")
    style.string = PICKER_CSS
    head.append(style)
    body = soup.body or soup
    script = soup.new_tag("script", nonce=nonce)
    script.string = PICKER_JS
    body.append(script)
    return str(soup), nonce


def message_page(text: str) -> tuple[str, str]:
    """A tiny page shown inside the frame when there's nothing to pick from yet."""
    nonce = secrets.token_urlsafe(16)
    body = f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{font:16px/1.5 system-ui,sans-serif;color:#4f5754;background:#f4f4f1;display:grid;place-items:center;height:100vh;margin:0;padding:24px;text-align:center}}
</style></head><body><p>{html_lib.escape(text)}</p></body></html>"""
    return body, nonce
