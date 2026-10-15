"""
views.py — turns database rows into the API's response shapes (WatchSummary, WatchDetail, SnapshotItem).

Who uses it: routes/watches.py, routes/templates.py, routes/stats.py.
Why a separate module: several routes return the same shapes; building them in one place keeps them
identical everywhere and keeps the route handlers short.
"""
from . import db, noise
from .config import settings
from .jobqueue import queue

WATCH_SELECT = """
SELECT w.*, t.url, t.domain, t.dial_seed, t.last_error, t.status AS target_status,
       (SELECT COUNT(*) FROM snapshots s WHERE s.watch_id = w.id) AS versions,
       (SELECT COUNT(*) FROM watches w2 WHERE w2.target_id = w.target_id) AS watchers
FROM watches w JOIN targets t ON t.id = w.target_id
"""


def rss_url(token: str) -> str:
    return f"{settings.base_url.rstrip('/')}/rss/{token}.xml"


async def number_info(watch_id: int) -> tuple[float | None, list[float]]:
    rows = await db.fetch_all("SELECT value FROM number_points WHERE watch_id = ? ORDER BY id DESC LIMIT 20", (watch_id,))
    values = [r["value"] for r in reversed(rows)]
    return (values[-1] if values else None), values


async def watch_summary(row: dict) -> dict:
    """WatchSummary: everything the dashboard needs for one dial or list row."""
    has_number = bool(row.get("number_selector") or row.get("number_regex"))
    latest, spark = await number_info(row["id"]) if has_number else (None, [])
    return {
        "id": row["id"],
        "name": row["name"] or row["domain"],
        "url": row["url"],
        "domain": row["domain"],
        "dial_seed": row["dial_seed"],
        "status": row["status"],
        "status_message": row["status_message"],
        "paused": bool(row["paused"]),
        "interval_minutes": row["interval_minutes"],
        "last_checked_at": row["last_checked_at"],
        "last_changed_at": row["last_changed_at"],
        "next_due_at": row["next_due_at"],
        "versions": row["versions"],
        "shared_watchers": row["watchers"],
        "is_running": row["target_id"] in queue.running,
        "is_queued": row["target_id"] in queue.queued,
        "number_latest": latest,
        "number_spark": spark,
        "flapping_until": row["flapping_until"],
    }


async def watch_detail(row: dict) -> dict:
    """WatchDetail: the summary plus every setting, learned rules and recent outcomes."""
    summary = await watch_summary(row)
    target = await db.fetch_one("SELECT volatile_rules FROM targets WHERE id = ?", (row["target_id"],))
    outcomes = await db.fetch_all(
        "SELECT outcome, started_at AS at FROM check_log WHERE watch_id = ? ORDER BY id DESC LIMIT 20", (row["id"],))
    return {
        **summary,
        "watch_selectors": db.from_json(row["watch_selectors"], []),
        "ignore_selectors": db.from_json(row["ignore_selectors"], []),
        "ignore_carousels": bool(row["ignore_carousels"]),
        "sensitivity": row["sensitivity"],
        "keywords": db.from_json(row["keywords"], []),
        "keyword_mode": row["keyword_mode"],
        "number_selector": row["number_selector"],
        "number_regex": row["number_regex"],
        "number_thresholds": db.from_json(row["number_thresholds"], {}),
        "alert_email": bool(row["alert_email"]),
        "alert_telegram": bool(row["alert_telegram"]),
        "alert_discord": bool(row["alert_discord"]),
        "rss_url": rss_url(row["rss_token"]),
        "volatile_rules": db.from_json(target["volatile_rules"] if target else None, []),
        "recent_outcomes": outcomes,
        "builtin_noise_selectors": noise.builtin_selector_groups(),
        "created_at": row["created_at"],
        "last_error": row["last_error"],
    }


async def get_watch_row(watch_id: int, user_id: int) -> dict | None:
    return await db.fetch_one(WATCH_SELECT + " WHERE w.id = ? AND w.user_id = ?", (watch_id, user_id))


def snapshot_item(row: dict, first_id: int | None) -> dict:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "summary": row["change_summary"],
        "ai_summary": row["ai_summary"],
        "added_lines": row["added_lines"],
        "removed_lines": row["removed_lines"],
        "change_score": row["change_score"],
        "thumbnail_url": f"/api/media/snapshot/{row['id']}/thumb.jpg" if row["thumbnail_path"] else None,
        "keyword_hit": row["keyword_hit"],
        "is_baseline": bool(row["is_baseline"]),
        "is_first": row["id"] == first_id,
    }
