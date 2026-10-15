"""
digest.py — the optional daily digest (requirement 7).

Who uses it: scheduler.py starts `digest_loop()`; routes/settings.py lets users switch to daily mode.
Depends on: alerts.py (senders + dedupe), db.

In "daily" mode, checker → alerts.on_change() stores each change as an `alerts` row with
status='queued_digest' instead of sending it. Every 10 minutes this loop looks at each daily-mode user:
once their local clock has passed their digest hour (e.g. 9 AM Asia/Kolkata) and they haven't had
today's digest yet, it sends ONE message grouping every queued change by page, then marks those rows
sent. If nothing changed, nothing is sent. The digest itself has a dedupe key (user + date + channel),
so a restart can't send it twice.
"""
import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from . import alerts, db
from .alerts import AlertMessage

log = logging.getLogger("changewatch.digest")
LOOP_S = 600


def user_now(user: dict) -> datetime:
    try:
        return datetime.now(ZoneInfo(user.get("timezone") or "Asia/Kolkata"))
    except Exception:
        return datetime.now(ZoneInfo("Asia/Kolkata"))


async def send_digest(user: dict, force: bool = False) -> int:
    """Send one user's digest if it's due (or if forced). Returns how many changes it contained."""
    local = user_now(user)
    today = local.date().isoformat()
    if not force and (local.hour < user["digest_hour"] or user["last_digest_date"] == today):
        return 0
    rows = await db.fetch_all(
        "SELECT a.id, a.payload, a.watch_id FROM alerts a WHERE a.user_id = ? AND a.status = 'queued_digest' ORDER BY a.id",
        (user["id"],))
    await db.execute("UPDATE users SET last_digest_date = ? WHERE id = ?", (today, user["id"]))
    if not rows:
        return 0
    by_page: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        p = db.from_json(row["payload"], {})
        by_page[p.get("name", "Page")].append(p)
    preview: list[tuple[str, str]] = []
    for name, items in by_page.items():
        for item in items[-3:]:
            preview.append(("+", f"{name}: {item.get('summary', 'changed')}"))
    total = len(rows)
    msg = AlertMessage(
        kind="change", page_name="Daily digest", page_url=alerts.app_link("/"),
        headline=f"Your ChangeWatch digest: {total} change{'s' if total != 1 else ''} on {len(by_page)} page{'s' if len(by_page) != 1 else ''}",
        summary="Here's what changed since your last digest. Open ChangeWatch for the full comparisons.",
        link=alerts.app_link("/activity"), when=alerts.local_time(user),
        added=sum(int(db.from_json(r["payload"], {}).get("added", 0)) for r in rows),
        removed=sum(int(db.from_json(r["payload"], {}).get("removed", 0)) for r in rows),
        preview=preview[:20],
    )
    channels = ["email"]
    if user.get("telegram_chat_id"):
        channels.append("telegram")
    if user.get("discord_webhook_url"):
        channels.append("discord")
    for channel in channels:
        alert_id = await alerts.claim(user, None, None, "change", channel, f"digest:{user['id']}:{today}:{channel}",
                                      payload={"digest": True, "count": total})
        if alert_id is None:
            continue
        reason = alerts.channel_ready(channel, user)
        if reason:
            await db.execute("UPDATE alerts SET status = 'failed', error = ? WHERE id = ?", (reason, alert_id))
            continue
        alerts.spawn(alerts.deliver(alert_id, channel, user, msg))
    ids = [r["id"] for r in rows]
    marks = ",".join("?" * len(ids))
    await db.execute(f"UPDATE alerts SET status = 'sent', sent_at = ? WHERE id IN ({marks})", (db.now_iso(), *ids))
    return total


async def digest_loop() -> None:
    await asyncio.sleep(30)
    while True:
        try:
            users = await db.fetch_all("SELECT * FROM users WHERE digest_mode = 'daily'")
            for user in users:
                sent = await send_digest(user)
                if sent:
                    log.info("Sent digest with %s changes to user %s", sent, user["id"])
        except Exception:
            log.exception("Digest loop failed")
        await asyncio.sleep(LOOP_S)
