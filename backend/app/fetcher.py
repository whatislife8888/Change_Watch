"""
fetcher.py — renders a page in headless Chromium and classifies the result (requirement 1 + Q1).

Who uses it: checker.py (every check), main.py (start/stop, health), routes/public.py (/healthz).
Depends on: Playwright (async API), security.py (SSRF filter for every sub-request), config.

One shared browser runs for the whole app (starting Chromium takes ~1 s; a fresh *context* per check
takes ~20 ms). Each check gets a brand-new BrowserContext — like a private window — so no cookies or
storage ever carry over between checks ("no stored credentials").

Classification (design question 1 — "is an outage or CAPTCHA a change?" No):
  ok       — a normal page
  error    — network/DNS failure, timeout, HTTP 5xx, 404/410, other 4xx
  blocked  — HTTP 401/403/429, or a bot wall ("Just a moment", reCAPTCHA, Cloudflare Turnstile...)
Errors and blocks never become snapshots, so the last good version stays the baseline.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from playwright.async_api import Browser, Error as PlaywrightError, Playwright, Route, Request
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

from . import security
from .config import settings

log = logging.getLogger("changewatch.fetcher")

VIEWPORT = {"width": 1366, "height": 900}
MAX_SCREENSHOT_HEIGHT = 8000
RENDER_TIMEOUT_S = 45
GOTO_TIMEOUT_MS = 30_000
NETWORKIDLE_TIMEOUT_MS = 8_000

# Ad/analytics hosts we never load: faster renders and fewer rotating ads in screenshots.
BLOCKED_HOSTS = (
    "doubleclick.net", "googlesyndication.com", "google-analytics.com", "googletagmanager.com", "facebook.net",
    "adservice.google.com", "taboola.com", "outbrain.com", "hotjar.com", "googleadservices.com", "amazon-adsystem.com",
    "criteo.com", "criteo.net", "scorecardresearch.com", "quantserve.com", "adnxs.com", "moatads.com", "pubmatic.com",
    "rubiconproject.com", "segment.io", "segment.com", "mixpanel.com", "clarity.ms", "newrelic.com", "nr-data.net",
    "fullstory.com", "intercomcdn.com", "connect.facebook.net", "bat.bing.com", "ads-twitter.com", "static.ads-twitter.com",
)
BLOCKED_RESOURCE_TYPES = {"media", "font"}

# Freeze animations before the screenshot so two renders of the same page look identical.
FREEZE_CSS = "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}"

BOT_WALL_PHRASES = (
    "just a moment", "attention required", "verify you are human", "verifying you are human", "captcha",
    "access denied", "unusual traffic", "are you a robot", "checking your browser", "please verify you are a human",
    "ddos protection by", "request unsuccessful. incapsula", "pardon our interruption",
)
STRONG_BOT_SELECTORS = ("#challenge-form", '[class*="cf-turnstile"]', "#cf-challenge-running", "#px-captcha")
WEAK_BOT_SELECTORS = ('iframe[src*="recaptcha"]', 'iframe[src*="hcaptcha"]', 'iframe[src*="captcha"]')

# Collected inside the page: bounding boxes (in page coordinates) for every selector a watch needs.
BOXES_JS = """
(selectors) => {
  const out = {};
  for (const sel of selectors) {
    let nodes;
    try { nodes = document.querySelectorAll(sel); } catch (e) { continue; }
    let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
    for (const n of nodes) {
      const r = n.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      x1 = Math.min(x1, r.left + scrollX); y1 = Math.min(y1, r.top + scrollY);
      x2 = Math.max(x2, r.right + scrollX); y2 = Math.max(y2, r.bottom + scrollY);
    }
    if (x2 > x1) out[sel] = {x: Math.round(x1), y: Math.round(y1), w: Math.round(x2 - x1), h: Math.round(y2 - y1)};
  }
  return out;
}
"""

BOT_CHECK_JS = """
([strong, weak]) => {
  const has = (list) => list.some((s) => { try { return !!document.querySelector(s); } catch (e) { return false; } });
  const text = (document.body ? document.body.innerText : '') || '';
  return { strong: has(strong), weak: has(weak), textLength: text.length, sample: text.slice(0, 3000).toLowerCase() };
}
"""


@dataclass
class RenderResult:
    """Everything one render produced, plus how we classified it."""
    outcome: str  # ok | error | blocked | timeout
    url: str
    http_status: int | None = None
    final_url: str | None = None
    headers: dict = field(default_factory=dict)
    html: str = ""
    raw_html: str = ""
    title: str = ""
    screenshot: bytes | None = None
    page_width: int = 0
    page_height: int = 0
    boxes: dict = field(default_factory=dict)
    duration_ms: int = 0
    error: str | None = None
    retryable: bool = False
    retry_after: float | None = None

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"


def parse_retry_after(value: str | None) -> float | None:
    """Retry-After is either seconds ("120") or an HTTP date. We support seconds and fall back to None."""
    if not value:
        return None
    try:
        return max(0.0, float(value.strip()))
    except ValueError:
        from email.utils import parsedate_to_datetime
        from datetime import datetime, timezone
        try:
            when = parsedate_to_datetime(value)
            return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            return None


def friendly_network_error(message: str) -> str:
    """Turn Chromium's net::ERR_* codes into plain words."""
    m = message or ""
    if "ERR_NAME_NOT_RESOLVED" in m:
        return "the address couldn't be found (DNS lookup failed)"
    if "ERR_CONNECTION_REFUSED" in m:
        return "the server refused the connection"
    if "ERR_CONNECTION_TIMED_OUT" in m or "ERR_TIMED_OUT" in m:
        return "the connection timed out"
    if "ERR_CERT" in m or "SSL" in m:
        return "its security certificate isn't valid"
    if "ERR_TOO_MANY_REDIRECTS" in m:
        return "it redirects in a loop"
    if "ERR_BLOCKED_BY_CLIENT" in m:
        return "it redirected to an address we don't fetch"
    if "ERR_INTERNET_DISCONNECTED" in m or "ERR_NETWORK" in m:
        return "the network was unavailable"
    return "the connection failed"


class Fetcher:
    """Owns the shared Chromium instance and renders pages with it."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._launch_lock = asyncio.Lock()
        # Global cap on simultaneous pages: each Chromium page can use 100+ MB of memory.
        self._pages = asyncio.Semaphore(settings.max_browser_pages)
        self.render_times_ms: list[int] = []

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        await self._ensure_browser()

    async def stop(self) -> None:
        if self._browser:
            try:
                await self._browser.close()
            except PlaywrightError:
                pass
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None

    @property
    def healthy(self) -> bool:
        return bool(self._browser and self._browser.is_connected())

    async def _ensure_browser(self) -> Browser:
        """Return the shared browser, (re)launching it if it isn't running — e.g. after a crash."""
        async with self._launch_lock:
            if self._browser and self._browser.is_connected():
                return self._browser
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            log.info("Launching Chromium")
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--disable-gpu", "--mute-audio", "--no-first-run"],
            )
            return self._browser

    def _route_handler(self, top_level_demo: bool):
        """Build the per-request filter: block heavy assets, ad hosts, and private-network destinations."""

        async def handle(route: Route, request: Request) -> None:
            try:
                if request.resource_type in BLOCKED_RESOURCE_TYPES:
                    await route.abort()
                    return
                host = (urlsplit(request.url).hostname or "").lower()
                if any(host == h or host.endswith("." + h) for h in BLOCKED_HOSTS):
                    await route.abort()
                    return
                if not await security.is_allowed_subrequest(request.url, top_level_demo):
                    await route.abort("blockedbyclient")
                    return
                await route.continue_()
            except PlaywrightError:
                # The page may have closed while we were deciding; nothing to do.
                pass

        return handle

    async def render(self, url: str, selectors: list[str]) -> RenderResult:
        """Render `url` and collect HTML, title, screenshot and element boxes, within 45 seconds."""
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(self._render(url, selectors), timeout=RENDER_TIMEOUT_S)
        except asyncio.TimeoutError:
            result = RenderResult("timeout", url, error=f"it took longer than {RENDER_TIMEOUT_S} seconds to load", retryable=True)
        except PlaywrightError as exc:
            # Usually a browser crash ("Target closed"). Retryable; the next attempt relaunches Chromium.
            log.warning("Browser error rendering %s: %s", url, exc)
            result = RenderResult("error", url, error="the browser crashed while loading it", retryable=True)
        result.duration_ms = int((time.monotonic() - started) * 1000)
        if result.ok:
            self.render_times_ms = (self.render_times_ms + [result.duration_ms])[-200:]
        return result

    async def _render(self, url: str, selectors: list[str]) -> RenderResult:
        async with self._pages:
            browser = await self._ensure_browser()
            context = await browser.new_context(
                viewport=VIEWPORT,
                user_agent=f"ChangeWatchBot/1.0 (+{settings.base_url.rstrip('/')}/bot)",
                service_workers="block",
                accept_downloads=False,
                java_script_enabled=True,
                locale="en-IN",
            )
            try:
                await context.route("**/*", self._route_handler(security.is_demo_url(url)))
                page = await context.new_page()
                try:
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
                except PlaywrightTimeout:
                    return RenderResult("timeout", url, error="it timed out after 30 seconds", retryable=True)
                except PlaywrightError as exc:
                    message = str(exc)
                    if "ERR_ABORTED" in message and "download" in message.lower():
                        return RenderResult("error", url, error="the link downloads a file instead of showing a page")
                    return RenderResult("error", url, error=friendly_network_error(message), retryable=True)

                try:
                    await page.wait_for_load_state("networkidle", timeout=NETWORKIDLE_TIMEOUT_MS)
                except PlaywrightTimeout:
                    pass  # Busy pages (live chat, analytics beacons) never go fully idle; that's fine.
                await page.wait_for_timeout(1000)

                final_url = page.url
                # Redirects aren't routed through our filter, so check where we ended up.
                if not security.is_demo_url(final_url):
                    try:
                        await security.check_url_is_public(final_url)
                    except security.UnsafeURL:
                        return RenderResult("error", url, final_url=final_url, error="it redirected to a private network address")

                status = response.status if response else None
                headers = await response.all_headers() if response else {}
                raw_html = ""
                if response is not None:
                    try:
                        raw_html = await response.text()
                    except PlaywrightError:
                        raw_html = ""

                classified = self._classify_status(url, status, headers)
                if classified is not None:
                    classified.final_url = final_url
                    return classified

                try:
                    await page.add_style_tag(content=FREEZE_CSS)
                except PlaywrightError:
                    pass  # Strict CSP pages may refuse injected styles; the screenshot is still useful.

                bot = await page.evaluate(BOT_CHECK_JS, [list(STRONG_BOT_SELECTORS), list(WEAK_BOT_SELECTORS)])
                title = await page.title()
                if self._looks_like_bot_wall(title, bot):
                    return RenderResult("blocked", url, http_status=status, final_url=final_url, title=title,
                                        error="it showed a bot check (CAPTCHA)")

                html = await page.content()
                height = await page.evaluate(
                    "Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)")
                width = VIEWPORT["width"]
                shot_height = max(1, min(int(height or VIEWPORT["height"]), MAX_SCREENSHOT_HEIGHT))
                screenshot = await page.screenshot(
                    type="png", full_page=True, clip={"x": 0, "y": 0, "width": width, "height": shot_height}, timeout=15_000)
                boxes = await page.evaluate(BOXES_JS, selectors) if selectors else {}

                return RenderResult(
                    "ok", url, http_status=status, final_url=final_url, headers=headers, html=html, raw_html=raw_html,
                    title=title, screenshot=screenshot, page_width=width, page_height=shot_height, boxes=boxes,
                )
            finally:
                await context.close()

    @staticmethod
    def _classify_status(url: str, status: int | None, headers: dict) -> RenderResult | None:
        """Map HTTP status codes to error/blocked. Returns None for normal 2xx/3xx pages."""
        if status is None or status < 400:
            return None
        retry_after = parse_retry_after(headers.get("retry-after"))
        if status in (401, 403):
            return RenderResult("blocked", url, http_status=status, error=f"it refused access (HTTP {status})")
        if status == 429:
            return RenderResult("blocked", url, http_status=status, error="it asked us to slow down (HTTP 429)",
                                retryable=True, retry_after=retry_after)
        if status in (404, 410):
            return RenderResult("error", url, http_status=status, error=f"the page wasn't found (HTTP {status})")
        if status >= 500:
            return RenderResult("error", url, http_status=status, error=f"the server had an error (HTTP {status})",
                                retryable=True, retry_after=retry_after if status == 503 else None)
        return RenderResult("error", url, http_status=status, error=f"the request was rejected (HTTP {status})")

    @staticmethod
    def _looks_like_bot_wall(title: str, bot: dict) -> bool:
        """Heuristics for a bot-check page. Never tries to solve it — we just report "blocked"."""
        title_l = (title or "").lower()
        if any(p in title_l for p in BOT_WALL_PHRASES):
            return True
        short_page = bot.get("textLength", 0) < 1500
        if bot.get("strong") and bot.get("textLength", 0) < 3000:
            return True
        if short_page and (bot.get("weak") or any(p in bot.get("sample", "") for p in BOT_WALL_PHRASES)):
            return True
        return False


fetcher = Fetcher()
