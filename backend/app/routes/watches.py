"""
routes/watches.py — everything about a user's watched pages: add, list, edit, delete, "Check now",
the version timeline, comparing versions, the check log, tracked numbers, learned rules, RSS and sharing.

Who uses it: the Dashboard, Add page, Page detail and Compare screens.
Depends on: urlnorm + security (validating URLs), jobqueue (enqueue checks), differ + visual_diff
(compare), views (response shapes), db.
"""
import asyncio
import secrets
import shutil
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Response

from .. import db, differ, noise, visual_diff
from ..auth import current_user
from ..config import settings
from ..errors import ApiError
from ..jobqueue import queue
from ..schemas import (MAX_INTERVAL, MIN_INTERVAL, CheckLogItem, CheckQueued, CompareResult, NumbersOut, RssOut,
                       ShareOut, SnapshotDetail, SnapshotItem, WatchCreate, WatchDetail, WatchPatch, WatchSummary)
from ..security import UnsafeURL, check_url_is_public
from ..urlnorm import InvalidURL, dial_seed, display_domain, normalise_url
from ..views import WATCH_SELECT, get_watch_row, rss_url, snapshot_item, watch_detail, watch_summary

router = APIRouter(prefix="/api", tags=["watches"])

MANUAL_COOLDOWN_S = 120


def check_interval(minutes: int) -> None:
    """Server-side validation (the form also checks, but the API must never trust the client)."""
    if not MIN_INTERVAL <= minutes <= MAX_INTERVAL:
        raise ApiError(422, "interval_out_of_range", "Choose an interval between 15 minutes and 24 hours.")


def clean_keywords(words: list[str]) -> list[str]:
    out = []
    for w in words:
        w = w.strip()
        if w and w.lower() not in [x.lower() for x in out]:
            out.append(w[:80])
    return out[:20]


async def find_or_create_target(url: str) -> int:
    """One Target per normalised URL, however many users watch it (design question 2).

    INSERT OR IGNORE + SELECT is race-safe: if two users add the same URL at the same instant, the
    UNIQUE constraint on targets.url lets only one insert win, and both then read the same row.
    """
    await db.execute(
        "INSERT OR IGNORE INTO targets (url, domain, dial_seed, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
        (url, display_domain(url), dial_seed(url), db.now_iso()),
    )
    row = await db.fetch_one("SELECT id FROM targets WHERE url = ?", (url,))
    assert row is not None
    return row["id"]


async def load_watch(watch_id: int, user: dict) -> dict:
    row = await get_watch_row(watch_id, user["id"])
    if not row:
        raise ApiError(404, "watch_not_found", "That page isn't in your list.")
    return row


async def create_watch_for(user: dict, body: WatchCreate, extra: dict | None = None) -> dict:
    """Shared by "Add page" and "Import a shared setup"."""
    check_interval(body.interval_minutes)
    try:
        url = normalise_url(body.url)
    except InvalidURL as exc:
        raise ApiError(422, "invalid_url", str(exc)) from exc
    try:
        await check_url_is_public(url)
    except UnsafeURL as exc:
        raise ApiError(422, "unsafe_url", str(exc)) from exc
    target_id = await find_or_create_target(url)
    existing = await db.fetch_one("SELECT id FROM watches WHERE user_id = ? AND target_id = ?", (user["id"], target_id))
    if existing:
        raise ApiError(409, "already_watching", "You're already watching this page.", extra={"watch_id": existing["id"]})
    extra = extra or {}
    watch_id = await db.execute(
        """INSERT INTO watches (user_id, target_id, name, interval_minutes, sensitivity, keywords, keyword_mode,
               alert_email, alert_telegram, alert_discord, watch_selectors, ignore_selectors, ignore_carousels,
               number_selector, number_regex, status, rss_token, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (user["id"], target_id, body.name.strip(), body.interval_minutes, body.sensitivity,
         db.to_json(clean_keywords(body.keywords)), body.keyword_mode, int(body.alert_email), int(body.alert_telegram),
         int(body.alert_discord), db.to_json(extra.get("watch_selectors", [])), db.to_json(extra.get("ignore_selectors", [])),
         int(extra.get("ignore_carousels", True)), extra.get("number_selector"), extra.get("number_regex"),
         secrets.token_urlsafe(18), db.now_iso()),
    )
    # A new watch makes the target due now; priority 0 so the first snapshot appears within seconds.
    await db.execute("UPDATE targets SET next_fetch_at = ? WHERE id = ?", (db.now_iso(), target_id))
    queue.enqueue(target_id, priority=0, reason="first check")
    row = await get_watch_row(watch_id, user["id"])
    assert row is not None
    return await watch_detail(row)


@router.get("/watches", response_model=list[WatchSummary])
async def list_watches(status: str | None = None, q: str | None = None, user: dict = Depends(current_user)) -> list[dict]:
    """All of the user's pages. Filters: status=changed_today|attention|paused|ok, q=search text."""
    sql = WATCH_SELECT + " WHERE w.user_id = ?"
    params: list = [user["id"]]
    if status == "attention":
        sql += " AND w.status IN ('error', 'blocked') AND w.paused = 0"
    elif status == "paused":
        sql += " AND w.paused = 1"
    elif status == "changed_today":
        sql += " AND w.last_changed_at >= ?"
        params.append((datetime.now(timezone.utc) - timedelta(hours=24)).isoformat())
    elif status == "ok":
        sql += " AND w.status = 'ok' AND w.paused = 0"
    if q:
        sql += " AND (w.name LIKE ? OR t.url LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY w.created_at DESC"
    rows = await db.fetch_all(sql, params)
    return [await watch_summary(r) for r in rows]


@router.post("/watches", response_model=WatchDetail, status_code=201)
async def create_watch(body: WatchCreate, user: dict = Depends(current_user)) -> dict:
    return await create_watch_for(user, body)


@router.get("/watches/{watch_id}", response_model=WatchDetail)
async def get_watch(watch_id: int, user: dict = Depends(current_user)) -> dict:
    return await watch_detail(await load_watch(watch_id, user))


@router.patch("/watches/{watch_id}", response_model=WatchDetail)
async def patch_watch(watch_id: int, body: WatchPatch, user: dict = Depends(current_user)) -> dict:
    row = await load_watch(watch_id, user)
    updates: dict = {}
    data = body.model_dump(exclude_unset=True)
    if "interval_minutes" in data and data["interval_minutes"] is not None:
        check_interval(data["interval_minutes"])
        updates["interval_minutes"] = data["interval_minutes"]
    for key in ("name", "sensitivity", "keyword_mode", "number_selector", "number_regex"):
        if key in data:
            value = data[key]
            updates[key] = value.strip() if isinstance(value, str) else value
    if "keywords" in data and data["keywords"] is not None:
        updates["keywords"] = db.to_json(clean_keywords(data["keywords"]))
    if "number_thresholds" in data and data["number_thresholds"] is not None:
        updates["number_thresholds"] = db.to_json(data["number_thresholds"])
    for key in ("alert_email", "alert_telegram", "alert_discord", "paused", "ignore_carousels"):
        if key in data and data[key] is not None:
            updates[key] = int(data[key])
    if "number_regex" in updates and updates["number_regex"]:
        import re
        try:
            re.compile(updates["number_regex"])
        except re.error as exc:
            raise ApiError(422, "invalid_regex", f"That pattern isn't valid: {exc}") from exc
    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        await db.execute(f"UPDATE watches SET {sets} WHERE id = ?", (*updates.values(), watch_id))
    if data.get("paused") is False and row["paused"]:
        # Resuming: check soon rather than waiting a whole interval.
        await db.execute("UPDATE targets SET next_fetch_at = ? WHERE id = ?", (db.now_iso(), row["target_id"]))
    if "interval_minutes" in updates:
        await db.execute("UPDATE watches SET next_due_at = NULL WHERE id = ? AND next_due_at > ?",
                         (watch_id, (datetime.now(timezone.utc) + timedelta(minutes=updates["interval_minutes"])).isoformat()))
    return await watch_detail(await load_watch(watch_id, user))


@router.delete("/watches/{watch_id}", status_code=204)
async def delete_watch(watch_id: int, user: dict = Depends(current_user)) -> Response:
    """Delete a watch; if nobody else watches the page, delete its Target and stored files too."""
    row = await load_watch(watch_id, user)
    snaps = await db.fetch_all("SELECT crop_path, thumbnail_path FROM snapshots WHERE watch_id = ?", (watch_id,))
    await db.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
    for s in snaps:
        for key in ("crop_path", "thumbnail_path"):
            if s[key]:
                (settings.data_dir / s[key]).unlink(missing_ok=True)
    remaining = await db.fetch_value("SELECT COUNT(*) FROM watches WHERE target_id = ?", (row["target_id"],))
    if remaining == 0:
        await db.execute("DELETE FROM targets WHERE id = ?", (row["target_id"],))
        shutil.rmtree(settings.data_dir / "fetches" / str(row["target_id"]), ignore_errors=True)
    return Response(status_code=204)


@router.post("/watches/{watch_id}/check", response_model=CheckQueued, status_code=202)
async def check_now(watch_id: int, user: dict = Depends(current_user)) -> dict:
    """Manual check: priority 0, but with a 2-minute cooldown per page (politeness, Q4)."""
    row = await load_watch(watch_id, user)
    target_id = row["target_id"]
    if queue.is_busy(target_id):
        queue.enqueue(target_id, priority=0, reason="check now")
        return {"queued": True, "attached": True}
    target = await db.fetch_one("SELECT last_fetched_at, status FROM targets WHERE id = ?", (target_id,))
    last = db.parse_iso(target["last_fetched_at"]) if target else None
    if last and target and target["status"] == "ok":
        since = (datetime.now(timezone.utc) - last).total_seconds()
        if since < MANUAL_COOLDOWN_S:
            wait = int(MANUAL_COOLDOWN_S - since) + 1
            raise ApiError(429, "cooldown", f"This page was checked {int(since)} seconds ago. Try again in {wait} seconds.",
                           headers={"Retry-After": str(wait)}, extra={"retry_after_seconds": wait})
    await db.execute("UPDATE watches SET next_due_at = NULL WHERE id = ?", (watch_id,))
    result = queue.enqueue(target_id, priority=0, reason="check now")
    return {"queued": True, "attached": result != "queued"}


@router.get("/watches/{watch_id}/snapshots", response_model=list[SnapshotItem])
async def list_snapshots(watch_id: int, limit: int = Query(30, ge=1, le=200), before: int | None = None,
                         user: dict = Depends(current_user)) -> list[dict]:
    await load_watch(watch_id, user)
    first_id = await db.fetch_value("SELECT MIN(id) FROM snapshots WHERE watch_id = ?", (watch_id,))
    sql = "SELECT * FROM snapshots WHERE watch_id = ?"
    params: list = [watch_id]
    if before:
        sql += " AND id < ?"
        params.append(before)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return [snapshot_item(r, first_id) for r in await db.fetch_all(sql, params)]


async def load_snapshot(snapshot_id: int, user: dict) -> dict:
    row = await db.fetch_one(
        "SELECT s.* FROM snapshots s JOIN watches w ON w.id = s.watch_id WHERE s.id = ? AND w.user_id = ?",
        (snapshot_id, user["id"]))
    if not row:
        raise ApiError(404, "snapshot_not_found", "That version doesn't exist.")
    return row


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotDetail)
async def get_snapshot(snapshot_id: int, user: dict = Depends(current_user)) -> dict:
    row = await load_snapshot(snapshot_id, user)
    first_id = await db.fetch_value("SELECT MIN(id) FROM snapshots WHERE watch_id = ?", (row["watch_id"],))
    return {
        **snapshot_item(row, first_id),
        "watch_id": row["watch_id"],
        "raw_text": row["raw_text"],
        "screenshot_url": f"/api/media/fetch/{row['fetch_id']}/screenshot.png" if row["fetch_id"] else None,
        "crop_url": f"/api/media/snapshot/{row['id']}/crop.png" if row["crop_path"] else None,
    }


@router.get("/watches/{watch_id}/compare", response_model=CompareResult)
async def compare(watch_id: int, a: int, b: int, user: dict = Depends(current_user)) -> dict:
    """Compare ANY two versions of a page: text ops (line + word level) and the visual diff."""
    watch = await load_watch(watch_id, user)
    snap_a = await load_snapshot(a, user)
    snap_b = await load_snapshot(b, user)
    if snap_a["watch_id"] != watch_id or snap_b["watch_id"] != watch_id:
        raise ApiError(400, "wrong_watch", "Both versions must belong to this page.")
    # Re-normalise both with the same rules and the same "today", so both sides are treated alike.
    target = await db.fetch_one("SELECT volatile_rules FROM targets WHERE id = ?", (watch["target_id"],))
    rules = db.from_json(target["volatile_rules"] if target else None, [])
    today = (db.parse_iso(snap_b["created_at"]) or datetime.now(timezone.utc)).date()
    na = noise.normalise_text(snap_a["raw_text"], watch["sensitivity"], rules, today)
    nb = noise.normalise_text(snap_b["raw_text"], watch["sensitivity"], rules, today)
    text = differ.diff_lines(na.norm_lines, nb.norm_lines, na.raw_lines, nb.raw_lines)

    fa = await db.fetch_one("SELECT * FROM fetches WHERE id = ?", (snap_a["fetch_id"],)) if snap_a["fetch_id"] else None
    fb = await db.fetch_one("SELECT * FROM fetches WHERE id = ?", (snap_b["fetch_id"],)) if snap_b["fetch_id"] else None
    visual = {"before_url": None, "after_url": None, "width": 1366, "height_before": 0, "height_after": 0,
              "regions": [], "changed_percent": 0.0, "shifted_by_px": 0, "diff_image_url": None, "available": False}
    if fa and fb and fa.get("screenshot_path") and fb.get("screenshot_path"):
        pa, pb = settings.data_dir / fa["screenshot_path"], settings.data_dir / fb["screenshot_path"]
        if pa.exists() and pb.exists():
            result = await asyncio.to_thread(visual_diff.cached_compare, a, b, pa, pb)
            visual = {
                "before_url": f"/api/media/fetch/{fa['id']}/screenshot.png",
                "after_url": f"/api/media/fetch/{fb['id']}/screenshot.png",
                "width": result.width, "height_before": result.height_before, "height_after": result.height_after,
                "regions": result.regions, "changed_percent": result.changed_percent, "shifted_by_px": result.shifted_by_px,
                "diff_image_url": f"/api/media/diff/{a}/{b}.png", "available": True,
            }

    def side(s: dict) -> dict:
        return {"id": s["id"], "created_at": s["created_at"], "summary": s["ai_summary"] or s["change_summary"]}

    return {"a": side(snap_a), "b": side(snap_b), "text": text, "visual": visual}


@router.get("/watches/{watch_id}/checks", response_model=list[CheckLogItem])
async def list_checks(watch_id: int, limit: int = Query(50, ge=1, le=200), user: dict = Depends(current_user)) -> list[dict]:
    """The check log, in plain outcomes. Only target-level rows and this watch's own rows (privacy)."""
    row = await load_watch(watch_id, user)
    return await db.fetch_all(
        "SELECT id, started_at, finished_at, outcome, attempt, detail, duration_ms, watch_id FROM check_log "
        "WHERE target_id = ? AND (watch_id IS NULL OR watch_id = ?) ORDER BY id DESC LIMIT ?",
        (row["target_id"], watch_id, limit))


@router.get("/watches/{watch_id}/numbers", response_model=NumbersOut)
async def get_numbers(watch_id: int, user: dict = Depends(current_user)) -> dict:
    await load_watch(watch_id, user)
    rows = await db.fetch_all(
        "SELECT recorded_at AS t, value, raw FROM number_points WHERE watch_id = ? ORDER BY id DESC LIMIT 500", (watch_id,))
    rows.reverse()
    changes = await db.fetch_all(
        "SELECT created_at FROM snapshots WHERE watch_id = ? AND is_baseline = 0 ORDER BY id DESC LIMIT 200", (watch_id,))
    values = [r["value"] for r in rows]
    first = values[0] if values else None
    latest = values[-1] if values else None
    change_pct = round((latest - first) / abs(first) * 100, 2) if first not in (None, 0) and latest is not None else None
    return {"points": rows, "min": min(values) if values else None, "max": max(values) if values else None,
            "latest": latest, "first": first, "change_pct": change_pct, "changed_at": [c["created_at"] for c in changes]}


@router.delete("/watches/{watch_id}/volatile-rules/{index}", response_model=WatchDetail)
async def delete_rule(watch_id: int, index: int, user: dict = Depends(current_user)) -> dict:
    """Forget one learned noise rule (rules belong to the page, so this affects every watcher)."""
    row = await load_watch(watch_id, user)
    target = await db.fetch_one("SELECT volatile_rules FROM targets WHERE id = ?", (row["target_id"],))
    rules = db.from_json(target["volatile_rules"] if target else None, [])
    if not 0 <= index < len(rules):
        raise ApiError(404, "rule_not_found", "That rule no longer exists.")
    rules.pop(index)
    await db.execute("UPDATE targets SET volatile_rules = ? WHERE id = ?", (db.to_json(rules), row["target_id"]))
    return await watch_detail(await load_watch(watch_id, user))


@router.post("/watches/{watch_id}/rss/regenerate", response_model=RssOut)
async def regenerate_rss(watch_id: int, user: dict = Depends(current_user)) -> dict:
    """New secret RSS link; the old one stops working (useful if a link was shared by mistake)."""
    await load_watch(watch_id, user)
    token = secrets.token_urlsafe(18)
    await db.execute("UPDATE watches SET rss_token = ? WHERE id = ?", (token, watch_id))
    return {"rss_url": rss_url(token)}


@router.post("/watches/{watch_id}/share", response_model=ShareOut)
async def share_setup(watch_id: int, user: dict = Depends(current_user)) -> dict:
    """Create a template link with this page's regions, ignore rules and keywords (never alert settings)."""
    row = await load_watch(watch_id, user)
    config = {
        "url": row["url"], "name": row["name"] or row["domain"],
        "watch_selectors": db.from_json(row["watch_selectors"], []),
        "ignore_selectors": db.from_json(row["ignore_selectors"], []),
        "ignore_carousels": bool(row["ignore_carousels"]),
        "keywords": db.from_json(row["keywords"], []), "keyword_mode": row["keyword_mode"],
        "sensitivity": row["sensitivity"], "interval_minutes": row["interval_minutes"],
        "number_selector": row["number_selector"], "number_regex": row["number_regex"],
    }
    token = secrets.token_urlsafe(12)
    await db.execute("INSERT INTO templates (token, owner_user_id, config, created_at) VALUES (?, ?, ?, ?)",
                     (token, user["id"], db.to_json(config), db.now_iso()))
    return {"template_url": f"{settings.base_url.rstrip('/')}/import/{token}", "token": token}
