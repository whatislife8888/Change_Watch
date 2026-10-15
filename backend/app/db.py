"""
db.py — the SQLite database: one shared connection, the schema, and tiny query helpers.

Who uses it: every module that reads or writes data (routes, checker, alerts, scheduler...).
Depends on: aiosqlite (an async wrapper that runs sqlite3 in a background thread so the
event loop never blocks on disk I/O).

Key decisions (explained for evaluators):
- WAL mode ("write-ahead log"): readers don't block the writer and vice versa, so the dashboard can
  read while a worker is saving a snapshot.
- Autocommit (isolation_level=None): every statement commits on its own. We rarely need multi-statement
  transactions; where we do, `transaction()` takes a lock so two coroutines can't interleave them.
- Migrations: an ordered list of SQL scripts plus a `schema_version` table. On startup we run only the
  scripts newer than the stored version, so restarts and upgrades never break an existing database.
"""
import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import aiosqlite

from .config import settings

# Each entry is one migration. Never edit an old entry once deployed — append a new one instead.
MIGRATIONS: list[str] = [
    # 1: initial schema
    """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL DEFAULT '',
        timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
        digest_mode TEXT NOT NULL DEFAULT 'instant',
        digest_hour INTEGER NOT NULL DEFAULT 9,
        last_digest_date TEXT,
        telegram_chat_id TEXT,
        telegram_bot_token TEXT,
        discord_webhook_url TEXT,
        is_admin INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL UNIQUE,
        domain TEXT NOT NULL,
        dial_seed TEXT NOT NULL,
        title TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        last_fetched_at TEXT,
        next_fetch_at TEXT,
        running_since TEXT,
        consecutive_failures INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        last_http_status INTEGER,
        etag TEXT,
        last_modified TEXT,
        static_html INTEGER NOT NULL DEFAULT 0,
        volatile_rules TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL
    );
    CREATE INDEX idx_targets_next_fetch ON targets(next_fetch_at);

    CREATE TABLE fetches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
        fetched_at TEXT NOT NULL,
        http_status INTEGER,
        final_url TEXT,
        html_path TEXT,
        screenshot_path TEXT,
        page_width INTEGER,
        page_height INTEGER,
        element_boxes TEXT NOT NULL DEFAULT '{}',
        duration_ms INTEGER
    );
    CREATE INDEX idx_fetches_target ON fetches(target_id);

    CREATE TABLE watches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        target_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
        name TEXT NOT NULL DEFAULT '',
        interval_minutes INTEGER NOT NULL,
        watch_selectors TEXT NOT NULL DEFAULT '[]',
        ignore_selectors TEXT NOT NULL DEFAULT '[]',
        ignore_carousels INTEGER NOT NULL DEFAULT 1,
        sensitivity TEXT NOT NULL DEFAULT 'medium',
        keywords TEXT NOT NULL DEFAULT '[]',
        keyword_mode TEXT NOT NULL DEFAULT 'off',
        number_selector TEXT,
        number_regex TEXT,
        number_thresholds TEXT NOT NULL DEFAULT '{}',
        alert_email INTEGER NOT NULL DEFAULT 1,
        alert_telegram INTEGER NOT NULL DEFAULT 0,
        alert_discord INTEGER NOT NULL DEFAULT 0,
        paused INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'pending',
        status_message TEXT,
        last_checked_at TEXT,
        last_changed_at TEXT,
        next_due_at TEXT,
        last_content_hash TEXT,
        flapping_until TEXT,
        rss_token TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    );
    CREATE INDEX idx_watches_target ON watches(target_id);
    CREATE INDEX idx_watches_user ON watches(user_id);

    CREATE TABLE snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        watch_id INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
        fetch_id INTEGER REFERENCES fetches(id) ON DELETE SET NULL,
        content_hash TEXT NOT NULL,
        text TEXT NOT NULL,
        raw_text TEXT NOT NULL,
        crop_path TEXT,
        thumbnail_path TEXT,
        created_at TEXT NOT NULL,
        change_summary TEXT,
        ai_summary TEXT,
        added_lines INTEGER NOT NULL DEFAULT 0,
        removed_lines INTEGER NOT NULL DEFAULT 0,
        change_score REAL NOT NULL DEFAULT 0,
        keyword_hit TEXT,
        is_baseline INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX idx_snapshots_watch ON snapshots(watch_id, id);

    CREATE TABLE alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        watch_id INTEGER REFERENCES watches(id) ON DELETE CASCADE,
        snapshot_id INTEGER REFERENCES snapshots(id) ON DELETE CASCADE,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        channel TEXT NOT NULL,
        dedupe_key TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        sent_at TEXT,
        created_at TEXT NOT NULL,
        error TEXT,
        payload TEXT
    );
    CREATE INDEX idx_alerts_watch ON alerts(watch_id, created_at);

    CREATE TABLE number_points (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        watch_id INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
        value REAL NOT NULL,
        raw TEXT NOT NULL,
        recorded_at TEXT NOT NULL
    );
    CREATE INDEX idx_numbers_watch ON number_points(watch_id, recorded_at);

    CREATE TABLE check_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
        watch_id INTEGER REFERENCES watches(id) ON DELETE CASCADE,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        outcome TEXT NOT NULL,
        attempt INTEGER NOT NULL DEFAULT 1,
        detail TEXT,
        duration_ms INTEGER
    );
    CREATE INDEX idx_checklog_target ON check_log(target_id, id);
    CREATE INDEX idx_checklog_watch ON check_log(watch_id, id);

    CREATE TABLE templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token TEXT NOT NULL UNIQUE,
        owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        config TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
]

_conn: aiosqlite.Connection | None = None
_tx_lock = asyncio.Lock()


def now_iso() -> str:
    """Current time as an ISO-8601 UTC string, e.g. '2026-10-15T09:30:00+00:00'."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    """Turn a stored ISO string back into an aware datetime (or None)."""
    if not value:
        return None
    return datetime.fromisoformat(value)


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def from_json(value: str | None, default: Any) -> Any:
    """Parse a JSON column, falling back to `default` for NULL or broken values."""
    if not value:
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


async def connect() -> None:
    """Open the shared connection, switch on WAL + foreign keys, and run pending migrations."""
    global _conn
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    _conn = await aiosqlite.connect(settings.data_dir / "changewatch.db", isolation_level=None)
    _conn.row_factory = aiosqlite.Row
    await _conn.execute("PRAGMA journal_mode=WAL")
    await _conn.execute("PRAGMA foreign_keys=ON")
    await _conn.execute("PRAGMA busy_timeout=5000")
    await _migrate()


async def close() -> None:
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


def conn() -> aiosqlite.Connection:
    if _conn is None:
        raise RuntimeError("Database is not connected yet")
    return _conn


async def _migrate() -> None:
    """Apply every migration whose number is above the stored schema_version."""
    db = conn()
    await db.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = await (await db.execute("SELECT version FROM schema_version")).fetchone()
    current = row["version"] if row else 0
    if row is None:
        await db.execute("INSERT INTO schema_version (version) VALUES (0)")
    for index, script in enumerate(MIGRATIONS, start=1):
        if index <= current:
            continue
        # executescript runs many statements; it commits any open transaction first.
        await db.executescript(script)
        await db.execute("UPDATE schema_version SET version = ?", (index,))


async def fetch_one(sql: str, params: tuple | list = ()) -> dict | None:
    """Run a SELECT and return the first row as a dict (or None)."""
    cursor = await conn().execute(sql, params)
    row = await cursor.fetchone()
    return dict(row) if row else None


async def fetch_all(sql: str, params: tuple | list = ()) -> list[dict]:
    """Run a SELECT and return every row as a list of dicts."""
    cursor = await conn().execute(sql, params)
    return [dict(r) for r in await cursor.fetchall()]


async def fetch_value(sql: str, params: tuple | list = ()) -> Any:
    """Run a SELECT that returns one value (e.g. COUNT(*))."""
    cursor = await conn().execute(sql, params)
    row = await cursor.fetchone()
    return row[0] if row else None


async def execute(sql: str, params: tuple | list = ()) -> int:
    """Run an INSERT/UPDATE/DELETE. Returns the new row id (for INSERTs)."""
    cursor = await conn().execute(sql, params)
    return cursor.lastrowid or 0


async def execute_rowcount(sql: str, params: tuple | list = ()) -> int:
    """Run an UPDATE/DELETE and return how many rows it touched."""
    cursor = await conn().execute(sql, params)
    return cursor.rowcount


async def insert_unique(sql: str, params: tuple | list = ()) -> int | None:
    """INSERT that may violate a UNIQUE constraint. Returns the row id, or None if it already existed.

    Why: alert dedupe relies on this — the UNIQUE dedupe_key makes the database the referee, so even
    two workers racing on the same change can only insert (and therefore send) one alert.
    """
    try:
        return await execute(sql, params)
    except sqlite3.IntegrityError:
        return None


@asynccontextmanager
async def transaction() -> AsyncIterator[aiosqlite.Connection]:
    """Run several statements atomically (all or nothing).

    Why the lock: all coroutines share one connection, so without it two coroutines could interleave
    their BEGIN/COMMIT and accidentally commit each other's half-finished work.
    """
    async with _tx_lock:
        db = conn()
        await db.execute("BEGIN")
        try:
            yield db
            await db.execute("COMMIT")
        except BaseException:
            await db.execute("ROLLBACK")
            raise
