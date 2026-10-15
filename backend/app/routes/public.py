"""
routes/public.py — endpoints that don't need a login: URL preview (live validation + live dial),
/healthz, /bot (about our crawler), /robots.txt and the demo page.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from .. import db
from ..auth import user_id_from_request
from ..config import settings
from ..demo import render_demo_page
from ..errors import ApiError
from ..fetcher import fetcher
from ..jobqueue import queue
from ..schemas import UrlPreviewIn, UrlPreviewOut
from ..security import client_ip, preview_limiter
from ..urlnorm import InvalidURL, dial_seed, display_domain, normalise_url

router = APIRouter(tags=["public"])


@router.post("/api/url/preview", response_model=UrlPreviewOut)
async def url_preview(body: UrlPreviewIn, request: Request) -> dict:
    """Validate + normalise a URL as the user types, and return its dial seed for the live dial.

    Deliberately cheap: no DNS lookup or fetch here (that happens when the page is actually added),
    so typing can't be used to probe networks.
    """
    if preview_limiter.hit(client_ip(request)):
        raise ApiError(429, "slow_down", "Slow down a little.")
    try:
        url = normalise_url(body.url)
    except InvalidURL as exc:
        return {"valid": False, "error": str(exc)}
    out = {"valid": True, "normalised_url": url, "domain": display_domain(url), "dial_seed": dial_seed(url)}
    target = await db.fetch_one("SELECT id FROM targets WHERE url = ?", (url,))
    if target:
        uid = user_id_from_request(request)
        out["other_watchers"] = await db.fetch_value(
            "SELECT COUNT(*) FROM watches WHERE target_id = ? AND user_id != ?", (target["id"], uid or 0))
        if uid:
            mine = await db.fetch_one("SELECT id FROM watches WHERE target_id = ? AND user_id = ?", (target["id"], uid))
            out["already_watching_id"] = mine["id"] if mine else None
    return out


@router.get("/healthz")
async def healthz() -> dict:
    """For Railway's health check and humans: is the database reachable, is Chromium running?"""
    try:
        await db.fetch_value("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return {"ok": db_ok, "db": db_ok, "browser": fetcher.healthy, "queue": queue.stats()}


@router.get("/api/health")
async def api_health() -> dict:
    return {"ok": True}


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots() -> str:
    return "User-agent: *\nAllow: /\nDisallow: /api/\n"


@router.get("/demo/changing-page", response_class=HTMLResponse)
async def demo_page() -> HTMLResponse:
    if not settings.allow_demo_page:
        raise ApiError(404, "not_found", "The demo page is turned off.")
    return HTMLResponse(render_demo_page(), headers={"Cache-Control": "no-store"})


@router.get("/bot", response_class=HTMLResponse)
async def bot_page() -> str:
    """Explains our crawler to site owners who see "ChangeWatchBot" in their logs."""
    gap = int(settings.domain_min_gap_seconds)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>ChangeWatchBot</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;max-width:640px;margin:48px auto;padding:0 20px;color:#141917;background:#f4f4f1}}
h1{{font-weight:400;font-family:Georgia,serif}}li{{margin:6px 0}}code{{background:#e2e4df;padding:1px 5px;border-radius:4px}}</style></head>
<body><h1>About ChangeWatchBot</h1>
<p>ChangeWatchBot visits public pages that people asked ChangeWatch to watch for changes, and tells them when
something meaningful changes. It identifies itself with the user agent <code>ChangeWatchBot/1.0 (+{settings.base_url.rstrip('/')}/bot)</code>.</p>
<h2>How it stays polite</h2>
<ul>
<li>It respects <code>robots.txt</code> (user agent <code>ChangeWatchBot</code>) and its <code>Crawl-delay</code>, cached for 24 hours.</li>
<li>It makes at most one request at a time to your site, at least {gap} seconds apart.</li>
<li>Each page is checked at most every 15 minutes, however many people watch it. Everyone shares one fetch.</li>
<li>When a page sends <code>ETag</code> or <code>Last-Modified</code>, it asks "has this changed?" first and skips the full load on <code>304</code>.</li>
<li>It honours <code>Retry-After</code> on 429 and 503 responses and backs off exponentially after errors.</li>
<li>It never logs in, never stores cookies, never fills in forms and never tries to solve CAPTCHAs.</li>
<li>It skips images-heavy extras like video, fonts and ad/analytics scripts.</li>
</ul>
<p>To opt out, add <code>User-agent: ChangeWatchBot</code> / <code>Disallow: /</code> to your robots.txt.</p>
</body></html>"""
