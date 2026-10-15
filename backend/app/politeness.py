"""
politeness.py — how ChangeWatch avoids hammering websites (design question 4).

Who uses it: checker.py (wraps every request to a site in `slot()` and checks robots.txt first),
routes/stats.py (shows per-domain "next allowed" times on /system).
Depends on: httpx (fetching robots.txt), urllib.robotparser, urlnorm (registrable domain).

Rules enforced here:
- One request at a time per registrable domain (an asyncio.Lock per domain).
- At least DOMAIN_MIN_GAP_SECONDS (default 10 s) between the end of one request and the start of the
  next to the same domain — or the site's own Crawl-delay if that is larger.
- robots.txt is fetched once and cached for 24 hours; disallowed pages are never fetched.
- Retry-After from 429/503 pushes that domain's next allowed time into the future.
"""
import asyncio
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator
from urllib import robotparser
from urllib.parse import urlsplit

import httpx

from . import security
from .config import settings
from .urlnorm import registrable_domain

log = logging.getLogger("changewatch.politeness")

ROBOTS_TTL_S = 24 * 3600
ROBOTS_ERROR_TTL_S = 3600
BOT_TOKEN = "ChangeWatchBot"


@dataclass
class RobotsEntry:
    fetched_at: float
    parser: robotparser.RobotFileParser | None  # None = no usable robots.txt (allow everything)
    crawl_delay: float | None
    ttl: float


class Politeness:
    """Per-domain rate limiter + robots.txt cache. One instance for the whole app."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.next_allowed: dict[str, float] = {}  # domain -> unix time
        self.busy: set[str] = set()
        self._robots: dict[str, RobotsEntry] = {}
        self._robots_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @property
    def user_agent(self) -> str:
        return f"{BOT_TOKEN}/1.0 (+{settings.base_url.rstrip('/')}/bot)"

    def gap_for(self, domain: str) -> float:
        """Seconds to wait between requests: the larger of our default and the site's Crawl-delay."""
        delays = [e.crawl_delay for origin, e in self._robots.items() if registrable_domain(origin) == domain and e.crawl_delay]
        return max([settings.domain_min_gap_seconds, *delays])

    @asynccontextmanager
    async def slot(self, url: str) -> AsyncIterator[None]:
        """Wait for our turn on this URL's domain, then hold the domain until the request finishes.

        Usage:  async with politeness.slot(url): await fetcher.render(url, ...)
        """
        domain = registrable_domain(url)
        async with self._locks[domain]:
            wait = self.next_allowed.get(domain, 0) - time.time()
            if wait > 0:
                await asyncio.sleep(wait)
            self.busy.add(domain)
            try:
                yield
            finally:
                self.busy.discard(domain)
                self.next_allowed[domain] = max(self.next_allowed.get(domain, 0), time.time() + self.gap_for(domain))

    def defer(self, url: str, seconds: float) -> None:
        """Honour Retry-After: don't contact this domain again for `seconds`."""
        domain = registrable_domain(url)
        self.next_allowed[domain] = max(self.next_allowed.get(domain, 0), time.time() + seconds)

    async def robots_allows(self, url: str) -> bool:
        """True if robots.txt lets ChangeWatchBot fetch this URL (cached 24 h per origin)."""
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        entry = await self._robots_entry(origin)
        if entry.parser is None:
            return True
        return entry.parser.can_fetch(BOT_TOKEN, url)

    async def _robots_entry(self, origin: str) -> RobotsEntry:
        async with self._robots_locks[origin]:
            entry = self._robots.get(origin)
            if entry and time.time() - entry.fetched_at < entry.ttl:
                return entry
            entry = await self._fetch_robots(origin)
            self._robots[origin] = entry
            return entry

    async def _fetch_robots(self, origin: str) -> RobotsEntry:
        """Download and parse robots.txt. Missing (4xx) = allow all. Errors = allow, retry in an hour."""
        url = origin + "/robots.txt"
        now = time.time()
        try:
            if not security.is_demo_url(origin + security.DEMO_PATH):
                await security.check_url_is_public(url)
            async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers={"User-Agent": self.user_agent}) as client:
                response = await client.get(url)
        except (httpx.HTTPError, security.UnsafeURL, OSError) as exc:
            log.info("robots.txt unavailable for %s: %s", origin, exc)
            return RobotsEntry(now, None, None, ROBOTS_ERROR_TTL_S)
        if response.status_code >= 400 or "html" in response.headers.get("content-type", ""):
            return RobotsEntry(now, None, None, ROBOTS_TTL_S if response.status_code < 500 else ROBOTS_ERROR_TTL_S)
        parser = robotparser.RobotFileParser()
        parser.parse(response.text.splitlines())
        delay = parser.crawl_delay(BOT_TOKEN)
        return RobotsEntry(now, parser, float(delay) if delay else None, ROBOTS_TTL_S)

    async def restore_from_db(self) -> int:
        """After a restart, remember when each site was last contacted.

        Why: the limiter lives in memory, so without this a deploy or crash would forget that we fetched
        a site a few seconds ago and could contact it again too soon.
        """
        from . import db  # local import: politeness is imported by db-free modules too

        rows = await db.fetch_all(
            "SELECT t.url, MAX(f.fetched_at) AS last FROM fetches f JOIN targets t ON t.id = f.target_id GROUP BY t.id")
        for row in rows:
            last = db.parse_iso(row["last"])
            if last is None:
                continue
            domain = registrable_domain(row["url"])
            # +1 s because stored times are rounded down to the second.
            until = last.timestamp() + 1 + self.gap_for(domain)
            self.next_allowed[domain] = max(self.next_allowed.get(domain, 0), until)
        return len(rows)

    def snapshot(self) -> list[dict]:
        """For /system: each known domain, when it may next be contacted, and whether it's busy now."""
        out = []
        for domain, at in sorted(self.next_allowed.items(), key=lambda kv: -kv[1])[:40]:
            out.append({"domain": domain, "next_allowed_at": at, "busy": domain in self.busy})
        return out


politeness = Politeness()
