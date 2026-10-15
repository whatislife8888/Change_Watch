"""
routes/stats.py — the dashboard's summary numbers, the Activity feed, and the admin /system view.
"""
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from .. import db
from ..auth import admin_user, current_user
from ..fetcher import fetcher
from ..jobqueue import queue
from ..politeness import politeness
from ..schemas import ActivityItem, AdminStats, OverviewStats

router = APIRouter(prefix="/api", tags=["stats"])

FAIL = {"error", "blocked", "timeout", "robots_disallowed"}


@router.get("/stats/overview", response_model=OverviewStats)
async def overview(user: dict = Depends(current_user)) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    rows = await db.fetch_all("SELECT target_id, status, paused, last_changed_at FROM watches WHERE user_id = ?", (user["id"],))
    return {
        "total": len(rows),
        "changed_today": sum(1 for r in rows if r["last_changed_at"] and r["last_changed_at"] >= since),
        "needs_attention": sum(1 for r in rows if r["status"] in ("error", "blocked") and not r["paused"]),
        "paused": sum(1 for r in rows if r["paused"]),
        "running": sum(1 for r in rows if r["target_id"] in queue.running),
        "waiting": sum(1 for r in rows if r["target_id"] in queue.queued),
    }


@router.get("/activity", response_model=list[ActivityItem])
async def activity(limit: int = Query(50, ge=1, le=200), before: str | None = None, watch_id: int | None = None,
                   kind: str | None = None, user: dict = Depends(current_user)) -> list[dict]:
    """Changes, errors, blocks and recoveries across the user's pages, newest first.

    Errors are reported once per run (when a page goes from OK to failing), not on every failed check.
    """
    watch_rows = await db.fetch_all(
        "SELECT w.id, w.name, t.domain, t.dial_seed FROM watches w JOIN targets t ON t.id = w.target_id WHERE w.user_id = ?",
        (user["id"],))
    info = {w["id"]: w for w in watch_rows}
    if watch_id is not None:
        info = {k: v for k, v in info.items() if k == watch_id}
    if not info:
        return []
    ids = list(info)
    marks = ",".join("?" * len(ids))
    items: list[dict] = []

    snaps = await db.fetch_all(
        f"""SELECT s.id, s.watch_id, s.created_at, s.change_summary, s.ai_summary, s.added_lines, s.removed_lines, s.is_baseline,
                   (SELECT MAX(p.id) FROM snapshots p WHERE p.watch_id = s.watch_id AND p.id < s.id) AS prev_id
            FROM snapshots s WHERE s.watch_id IN ({marks}) ORDER BY s.id DESC LIMIT 400""", ids)
    for s in snaps:
        w = info[s["watch_id"]]
        items.append({
            "kind": "baseline" if s["is_baseline"] or s["prev_id"] is None else "change",
            "at": s["created_at"], "watch_id": s["watch_id"], "watch_name": w["name"] or w["domain"], "domain": w["domain"],
            "dial_seed": w["dial_seed"], "summary": s["ai_summary"] or s["change_summary"] or "Changed",
            "snapshot_id": s["id"], "previous_snapshot_id": s["prev_id"], "added": s["added_lines"], "removed": s["removed_lines"],
        })

    logs = await db.fetch_all(
        f"SELECT watch_id, started_at, outcome, detail FROM check_log WHERE watch_id IN ({marks}) ORDER BY id DESC LIMIT 2000", ids)
    logs.reverse()
    last_state: dict[int, str] = {}
    for row in logs:
        state = "fail" if row["outcome"] in FAIL else "ok"
        prev = last_state.get(row["watch_id"], "ok")
        w = info[row["watch_id"]]
        base = {"at": row["started_at"], "watch_id": row["watch_id"], "watch_name": w["name"] or w["domain"],
                "domain": w["domain"], "dial_seed": w["dial_seed"]}
        if state == "fail" and prev == "ok":
            kind_ = "blocked" if row["outcome"] in ("blocked", "robots_disallowed") else "error"
            items.append({**base, "kind": kind_, "summary": row["detail"] or row["outcome"]})
        elif state == "ok" and prev == "fail":
            items.append({**base, "kind": "recovered", "summary": "Back to normal"})
        last_state[row["watch_id"]] = state

    if kind:
        wanted = {"changes": {"change", "baseline"}, "problems": {"error", "blocked", "recovered"}}.get(kind, {kind})
        items = [i for i in items if i["kind"] in wanted]
    if before:
        items = [i for i in items if i["at"] < before]
    items.sort(key=lambda i: i["at"], reverse=True)
    return items[:limit]


@router.get("/admin/stats", response_model=AdminStats)
async def admin_stats(_: dict = Depends(admin_user)) -> dict:
    """The engine, explained with numbers (for /system)."""
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    users = await db.fetch_value("SELECT COUNT(*) FROM users")
    watches = await db.fetch_value("SELECT COUNT(*) FROM watches")
    targets = await db.fetch_value("SELECT COUNT(*) FROM targets")
    outcomes = await db.fetch_all(
        "SELECT outcome, COUNT(*) AS n FROM check_log WHERE started_at >= ? AND watch_id IS NOT NULL GROUP BY outcome", (since,))
    counts = {r["outcome"]: r["n"] for r in outcomes}
    total = sum(counts.values()) or 1
    fetch_count = await db.fetch_value("SELECT COUNT(*) FROM fetches WHERE fetched_at >= ?", (since,))
    watch_evals = sum(counts.values())
    rules = await db.fetch_all("SELECT volatile_rules FROM targets")
    learned = sum(len(db.from_json(r["volatile_rules"], [])) for r in rules)
    times = fetcher.render_times_ms
    shared = await db.fetch_all(
        "SELECT t.domain, t.url, COUNT(w.id) AS watchers FROM targets t JOIN watches w ON w.target_id = t.id "
        "GROUP BY t.id HAVING watchers > 1 ORDER BY watchers DESC LIMIT 8")
    now = time.time()
    domains = [
        {"domain": d["domain"], "busy": d["busy"],
         "next_allowed_at": datetime.fromtimestamp(d["next_allowed_at"], timezone.utc).replace(microsecond=0).isoformat()
         if d["next_allowed_at"] > now else None}
        for d in politeness.snapshot()
    ]
    ok = counts.get("changed", 0) + counts.get("unchanged", 0) + counts.get("ignored_minor", 0) + counts.get("ignored_volatile", 0) + counts.get("not_modified", 0)
    return {
        "users": users, "watches": watches, "targets": targets,
        "sharing_ratio": round(watches / targets, 2) if targets else 0.0,
        "checks_24h": watch_evals, "outcome_counts": counts,
        "ok_rate": round(ok / total, 3),
        "error_rate": round((counts.get("error", 0) + counts.get("timeout", 0)) / total, 3),
        "blocked_rate": round((counts.get("blocked", 0) + counts.get("robots_disallowed", 0)) / total, 3),
        "avg_render_ms": round(sum(times) / len(times)) if times else None,
        "renders_saved_24h": max(0, watch_evals - (fetch_count or 0)),
        "queue": queue.stats(), "domains": domains, "learned_rules": learned,
        "top_shared": [dict(r) for r in shared],
    }
