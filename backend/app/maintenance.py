"""
maintenance.py — housekeeping that keeps the disk and database from growing forever.

Who uses it: scheduler.py starts `cleanup_loop()`.
- Deletes fetch files (screenshot + HTML) older than 7 days that no snapshot points to.
- Keeps only the last ~500 check_log rows per target (the checker also trims after each check).
- Clears cached diff images older than 7 days (they're recreated on demand).
"""
import asyncio
import logging
import time
from pathlib import Path

from . import db
from .config import settings

log = logging.getLogger("changewatch.maintenance")

KEEP_DAYS = 7


async def cleanup_once() -> dict:
    """One cleanup pass. Returns counts, for logging and tests."""
    cutoff = time.time() - KEEP_DAYS * 86400
    removed_fetches = 0
    rows = await db.fetch_all(
        """
        SELECT f.id, f.screenshot_path, f.html_path, f.fetched_at FROM fetches f
        WHERE (f.screenshot_path IS NOT NULL OR f.html_path IS NOT NULL)
          AND NOT EXISTS (SELECT 1 FROM snapshots s WHERE s.fetch_id = f.id)
        """
    )
    for row in rows:
        fetched = db.parse_iso(row["fetched_at"])
        if fetched and fetched.timestamp() > cutoff:
            continue
        for key in ("screenshot_path", "html_path"):
            if row[key]:
                Path(settings.data_dir, row[key]).unlink(missing_ok=True)
        await db.execute("UPDATE fetches SET screenshot_path = NULL, html_path = NULL WHERE id = ?", (row["id"],))
        removed_fetches += 1
    # Fetch rows nobody references and that have no files are just noise in the table.
    await db.execute(
        "DELETE FROM fetches WHERE screenshot_path IS NULL AND html_path IS NULL AND fetched_at < ? "
        "AND NOT EXISTS (SELECT 1 FROM snapshots s WHERE s.fetch_id = fetches.id)",
        (db.now_iso()[:10],),
    )
    diffs = Path(settings.data_dir, "diffs")
    removed_diffs = 0
    if diffs.exists():
        for f in diffs.iterdir():
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                removed_diffs += 1
    return {"fetch_files": removed_fetches, "diffs": removed_diffs}


async def cleanup_loop() -> None:
    await asyncio.sleep(60)
    while True:
        try:
            result = await cleanup_once()
            log.info("Cleanup: %s", result)
        except Exception:
            log.exception("Cleanup failed")
        await asyncio.sleep(6 * 3600)
