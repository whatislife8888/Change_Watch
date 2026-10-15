"""
rss.py — a private RSS 2.0 feed per watched page (bonus): GET /rss/{token}.xml

Who uses it: feed readers (Feedly, Inoreader, Thunderbird...). No login: the long random token in the
URL is the secret (it can be regenerated from the page's Settings if it leaks).
Each item is one version: title = summary, link = the compare view, guid = snapshot id + hash,
pubDate in RFC 822 format, description = the added/removed lines as HTML.
"""
import html
from email.utils import format_datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter
from fastapi.responses import Response

from . import db
from .config import settings
from .errors import ApiError
from .urlnorm import display_domain

router = APIRouter(tags=["rss"])


def _description(snap: dict, prev: dict | None) -> str:
    """Added/removed lines (vs the previous version) as a small HTML fragment."""
    if prev is None:
        return "<p>First version saved.</p>"
    old = set(prev["raw_text"].split("\n"))
    new = set(snap["raw_text"].split("\n"))
    added = [line for line in snap["raw_text"].split("\n") if line and line not in old][:10]
    removed = [line for line in prev["raw_text"].split("\n") if line and line not in new][:10]
    parts = [f"<p>{html.escape(snap['ai_summary'] or snap['change_summary'] or '')}</p>"]
    if added:
        parts.append("<p><b>Added</b></p><ul>" + "".join(f"<li>{html.escape(x[:300])}</li>" for x in added) + "</ul>")
    if removed:
        parts.append("<p><b>Removed</b></p><ul>" + "".join(f"<li><s>{html.escape(x[:300])}</s></li>" for x in removed) + "</ul>")
    return "".join(parts)


@router.get("/rss/{token}.xml", include_in_schema=False)
async def feed(token: str) -> Response:
    watch = await db.fetch_one(
        "SELECT w.*, t.url FROM watches w JOIN targets t ON t.id = w.target_id WHERE w.rss_token = ?", (token,))
    if not watch:
        raise ApiError(404, "feed_not_found", "This feed link doesn't exist (it may have been replaced).")
    snaps = await db.fetch_all("SELECT * FROM snapshots WHERE watch_id = ? ORDER BY id DESC LIMIT 31", (watch["id"],))
    base = settings.base_url.rstrip("/")
    name = watch["name"] or display_domain(watch["url"])
    items = []
    for i, snap in enumerate(snaps[:30]):
        prev = snaps[i + 1] if i + 1 < len(snaps) else None
        link = f"{base}/pages/{watch['id']}/compare?a={prev['id']}&b={snap['id']}" if prev else f"{base}/pages/{watch['id']}"
        title = snap["ai_summary"] or snap["change_summary"] or "Changed"
        published = db.parse_iso(snap["created_at"])
        items.append(
            "<item>"
            f"<title>{escape(title)}</title>"
            f"<link>{escape(link)}</link>"
            f"<guid isPermaLink=\"false\">{snap['id']}-{snap['content_hash'][:16]}</guid>"
            f"<pubDate>{format_datetime(published) if published else ''}</pubDate>"
            f"<description>{escape(_description(snap, prev))}</description>"
            "</item>"
        )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        f"<title>{escape(name)} on ChangeWatch</title>"
        f"<link>{escape(base + '/pages/' + str(watch['id']))}</link>"
        f"<description>Changes to {escape(watch['url'])}, with noise filtered out.</description>"
        "<generator>ChangeWatch</generator>"
        + "".join(items) + "</channel></rss>"
    )
    return Response(body, media_type="application/rss+xml", headers={"Cache-Control": "public, max-age=300"})
