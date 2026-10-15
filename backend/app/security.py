"""
security.py — keeps ChangeWatch from being turned against private networks or its own users.

Who uses it: watch creation and every fetch (SSRF guard), the fetcher's sub-request filter, main.py
(Origin check middleware), auth routes (login rate limit).

Three protections live here:
1. SSRF guard. SSRF ("server-side request forgery") is when an attacker asks our server to fetch a URL
   like http://169.254.169.254/ (the cloud metadata service) or http://192.168.0.1/ (a router) and
   then reads the result through our screenshots. We resolve every hostname ourselves and refuse
   anything that isn't a public internet address. We re-check on every fetch because DNS can change.
2. Origin check (CSRF protection). Browsers attach the `Origin` header to POST/PUT/PATCH/DELETE
   requests. If it's not our own site, someone else's page is trying to act with our user's cookie,
   so we refuse.
3. Rate limits. A tiny in-memory sliding window per IP (10 logins/minute) slows password guessing.
"""
import asyncio
import ipaddress
import socket
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .config import settings
from .errors import error_json

DEMO_PATH = "/demo/changing-page"
# Our own demo pages (only these paths on our own host get past the SSRF guard, and only when enabled):
# the noisy/changing page, a fake bot wall and a fake outage, so design question 1 can be shown live.
DEMO_PATHS = {DEMO_PATH, "/demo/bot-check", "/demo/outage"}
_DNS_TTL_SECONDS = 300
_dns_cache: dict[str, tuple[float, list[str]]] = {}


class UnsafeURL(ValueError):
    """Raised (with a user-facing message) when a URL points somewhere we must not fetch."""


def is_public_ip(ip_text: str) -> bool:
    """True only for ordinary public internet addresses."""
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    # IPv6 addresses can wrap an IPv4 address (::ffff:10.0.0.1); check the inner one too.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
        or ip.is_reserved or ip.is_unspecified or not ip.is_global
    )


async def resolve_host(host: str) -> list[str]:
    """Resolve a hostname to IP addresses, cached for 5 minutes.

    Why cache: the browser makes dozens of sub-requests per page to the same few hosts; resolving each
    one again would be slow. 5 minutes is short enough to notice DNS changes.
    """
    now = time.monotonic()
    cached = _dns_cache.get(host)
    if cached and now - cached[0] < _DNS_TTL_SECONDS:
        return cached[1]
    try:
        ipaddress.ip_address(host)
        ips = [host]
    except ValueError:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        ips = sorted({info[4][0] for info in infos})
    _dns_cache[host] = (now, ips)
    return ips


def own_hosts() -> set[str]:
    """Host[:port] values that are this app itself (used only for the demo page whitelist)."""
    hosts = {urlsplit(settings.base_url).netloc.lower(), "localhost:8000", "127.0.0.1:8000", "localhost:5173", "127.0.0.1:5173"}
    return hosts


def is_demo_url(url: str) -> bool:
    """The one exception to the SSRF guard: our own /demo/* pages, when ALLOW_DEMO_PAGE is on."""
    if not settings.allow_demo_page:
        return False
    parts = urlsplit(url)
    return parts.path in DEMO_PATHS and parts.netloc.lower() in own_hosts()


async def check_url_is_public(url: str) -> None:
    """Raise UnsafeURL unless the URL is an http(s) address on the public internet."""
    if is_demo_url(url):
        return
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeURL("Only http and https pages can be watched.")
    if parts.username or parts.password:
        raise UnsafeURL("Links with a username or password can't be watched.")
    host = (parts.hostname or "").lower()
    if not host or host == "localhost" or host.endswith(".localhost") or host.endswith(".local") or host.endswith(".internal"):
        raise UnsafeURL("That address points to a private network, so it can't be watched.")
    try:
        ips = await resolve_host(host)
    except (socket.gaierror, UnicodeError, OSError) as exc:
        raise UnsafeURL(f"We couldn't find {host}. Check the address for typos.") from exc
    if not ips or not all(is_public_ip(ip) for ip in ips):
        raise UnsafeURL("That address points to a private network, so it can't be watched.")


async def is_allowed_subrequest(url: str, top_level_demo: bool) -> bool:
    """Decide whether the headless browser may load a sub-resource (image, script, CSS...).

    Called by the fetcher for every request a page makes. A public page could embed
    <img src="http://169.254.169.254/latest/meta-data/"> — this is where we stop that.
    """
    parts = urlsplit(url)
    if parts.scheme in ("data", "blob", "about"):
        return True
    if parts.scheme not in ("http", "https"):
        return False
    if top_level_demo and is_demo_url(url):
        return True
    host = (parts.hostname or "").lower()
    if not host or host == "localhost":
        return False
    try:
        ips = await resolve_host(host)
    except (socket.gaierror, UnicodeError, OSError):
        return False
    return bool(ips) and all(is_public_ip(ip) for ip in ips)


# ---------- Origin check (CSRF) ----------

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def allowed_origins() -> set[str]:
    origins = {settings.base_origin.lower()}
    origins.update(o.lower() for o in settings.cors_origin_list)
    if not settings.is_https:
        # Local development: the Vite dev server and the backend itself.
        origins.update({"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"})
    return origins


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """Reject unsafe requests to /api whose Origin header isn't one of ours."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in UNSAFE_METHODS and request.url.path.startswith("/api/"):
            origin = (request.headers.get("origin") or "").rstrip("/").lower()
            if origin not in allowed_origins():
                return error_json(403, "bad_origin", "This request didn't come from ChangeWatch, so it was refused.")
        return await call_next(request)


# ---------- rate limiting ----------

class RateLimiter:
    """Sliding-window limiter: at most `limit` events per `window` seconds per key (usually an IP)."""

    def __init__(self, limit: int, window: float):
        self.limit = limit
        self.window = window
        self.events: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> float | None:
        """Record one event. Returns None if allowed, or the seconds to wait if over the limit."""
        now = time.monotonic()
        q = self.events[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return max(1.0, self.window - (now - q[0]))
        q.append(now)
        return None


login_limiter = RateLimiter(limit=10, window=60)
preview_limiter = RateLimiter(limit=90, window=60)
signup_limiter = RateLimiter(limit=10, window=3600)


def client_ip(request: Request) -> str:
    """Best guess at the caller's IP. Railway puts the real client IP first in X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
