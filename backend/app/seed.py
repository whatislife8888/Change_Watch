"""
seed.py — create a demo account with a few watched pages:  python -m app.seed

Who uses it: you, once, on a fresh database (locally or on the server) so evaluators can log in and see
real data straight away. The pages are real; the server checks them for real as soon as it runs —
this script only creates the account and the subscriptions, never fake snapshots.

Demo login (printed at the end):  demo@changewatch.app / watch-the-dials
"""
import asyncio
import secrets
from urllib.parse import urlsplit

from . import db
from .auth import hash_password
from .config import settings
from .urlnorm import dial_seed, display_domain, normalise_url

DEMO_EMAIL = "demo@changewatch.app"
DEMO_PASSWORD = "watch-the-dials"


def demo_page_url() -> str:
    """Locally the engine reaches the demo page on :8000; in production it's on BASE_URL itself."""
    host = urlsplit(settings.base_url).hostname or ""
    if host in ("localhost", "127.0.0.1"):
        return "http://localhost:8000/demo/changing-page"
    return settings.base_url.rstrip("/") + "/demo/changing-page"


WATCHES = [
    # (url, name, interval minutes, extra settings)
    (demo_page_url(), "Campus Tech Fest notice board", 15, {"sensitivity": "medium"}),
    ("https://example.com", "Example Domain", 1440, {}),
    ("https://en.wikipedia.org/wiki/Mechanical_watch", "Wikipedia: Mechanical watch", 360,
     {"watch_selectors": ["#mw-content-text"]}),
    ("https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html", "A Light in the Attic (price)", 60,
     {"number_selector": "p.price_color", "number_thresholds": {"below": 40}}),
    ("https://news.ycombinator.com/", "Hacker News front page", 30, {"sensitivity": "low", "keyword_mode": "any",
                                                                    "keywords": ["India", "open source"]}),
]


async def seed() -> None:
    await db.connect()
    try:
        user = await db.fetch_one("SELECT * FROM users WHERE email = ?", (DEMO_EMAIL,))
        if user is None:
            first = await db.fetch_value("SELECT COUNT(*) FROM users") == 0
            uid = await db.execute(
                "INSERT INTO users (email, password_hash, display_name, is_admin, created_at) VALUES (?, ?, ?, ?, ?)",
                (DEMO_EMAIL, hash_password(DEMO_PASSWORD), "Demo", 1 if first else 0, db.now_iso()))
            print(f"Created demo user {DEMO_EMAIL}")
        else:
            uid = user["id"]
            print(f"Demo user {DEMO_EMAIL} already exists")
        for raw, name, interval, extra in WATCHES:
            url = normalise_url(raw)
            await db.execute(
                "INSERT OR IGNORE INTO targets (url, domain, dial_seed, status, created_at, next_fetch_at) VALUES (?, ?, ?, 'pending', ?, ?)",
                (url, display_domain(url), dial_seed(url), db.now_iso(), db.now_iso()))
            target = await db.fetch_one("SELECT id FROM targets WHERE url = ?", (url,))
            assert target is not None
            if await db.fetch_one("SELECT id FROM watches WHERE user_id = ? AND target_id = ?", (uid, target["id"])):
                continue
            await db.execute(
                """INSERT INTO watches (user_id, target_id, name, interval_minutes, sensitivity, watch_selectors,
                       number_selector, number_thresholds, keyword_mode, keywords, rss_token, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (uid, target["id"], name, interval, extra.get("sensitivity", "medium"),
                 db.to_json(extra.get("watch_selectors", [])), extra.get("number_selector"),
                 db.to_json(extra.get("number_thresholds", {})), extra.get("keyword_mode", "off"),
                 db.to_json(extra.get("keywords", [])), secrets.token_urlsafe(18), db.now_iso()))
            print(f"  watching {url}")
        print(f"\nLog in with {DEMO_EMAIL} / {DEMO_PASSWORD}. The running server checks these pages within a minute.")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(seed())
