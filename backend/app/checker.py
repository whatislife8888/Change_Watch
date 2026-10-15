"""
checker.py — one check of one Target, from fetch to alerts. The heart of the engine.

Who uses it: jobqueue.py workers call `check_target()`; routes/picker.py calls `rebaseline()`.
Depends on: almost everything — fetcher, politeness, extract, noise, differ, visual_diff, numbers,
summarize, alerts, events, db.

What happens in one check (design questions in brackets):
 1. Load the target and its un-paused watches; pick the watches that are due.
 2. Re-check the SSRF guard (DNS can change) and robots.txt.                         [Q4]
 3. If the page is plain server HTML and we have an ETag/Last-Modified, ask the server
    "has it changed?" first. A 304 answer means we skip the browser entirely.          [Q2, Q4]
 4. Wait for our turn on the domain (politeness), then render once in Chromium.        [Q4]
 5. Classify: error / blocked / ok. Errors and blocks never become snapshots.          [Q1]
 6. Evaluate EVERY due watch from that one render — each with its own regions,
    ignore rules and sensitivity.                                                       [Q2]
 7. If a watch looks changed, re-fetch ~10 s later. Lines that differ between the two
    fetches are "volatile" and become learned rules; only changes present in both
    fetches count.                                                                      [Q3]
 8. Significant changes become snapshots (text + screenshot crop + thumbnail), with a
    summary, keyword check and flapping guard, then alerts and live events.             [Q3]
"""
import gzip
import hashlib
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

from . import alerts, db, differ, extract, noise, numbers, security, summarize, visual_diff
from .config import data_path, settings
from .events import bus
from .fetcher import RenderResult, fetcher
from .jobqueue import AttemptResult
from .politeness import politeness
from .scheduler import iso_in, jittered
from .urlnorm import display_domain

log = logging.getLogger("changewatch.checker")

MAX_RULES = 50
CHECK_LOG_KEEP = 500
STATUS_ALERT_AFTER = 3
FLAP_WINDOW_H = 6
FLAP_COUNT = 4


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def effective_interval_s(watches: list[dict]) -> float:
    """A target is fetched as often as its most frequent watcher wants (never below 15 minutes)."""
    minutes = min((w["interval_minutes"] for w in watches), default=60)
    return settings.minutes_to_seconds(max(15, minutes))


def effective_sensitivity(watch: dict, now: datetime) -> str:
    """The flapping guard raises the threshold one level while `flapping_until` is in the future."""
    until = db.parse_iso(watch.get("flapping_until"))
    if until and until > now:
        return noise.stricter(watch["sensitivity"])
    return watch["sensitivity"]


def is_due(watch: dict, now: datetime) -> bool:
    """A watch is evaluated if its own interval has (nearly) elapsed. The 15% tolerance absorbs jitter."""
    due = db.parse_iso(watch.get("next_due_at"))
    if due is None:
        return True
    tolerance = settings.minutes_to_seconds(watch["interval_minutes"]) * 0.15 + 5
    return due <= now + timedelta(seconds=tolerance)


async def log_check(target_id: int, watch_id: int | None, outcome: str, attempt: int, detail: str | None,
                    started_iso: str, duration_ms: int) -> None:
    await db.execute(
        "INSERT INTO check_log (target_id, watch_id, started_at, finished_at, outcome, attempt, detail, duration_ms) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (target_id, watch_id, started_iso, db.now_iso(), outcome, attempt, detail, duration_ms),
    )


async def trim_check_log(target_id: int) -> None:
    await db.execute(
        "DELETE FROM check_log WHERE target_id = ? AND id NOT IN "
        "(SELECT id FROM check_log WHERE target_id = ? ORDER BY id DESC LIMIT ?)",
        (target_id, target_id, CHECK_LOG_KEEP),
    )


def friendly_failure(domain: str, outcome: str, error: str | None) -> str:
    """Plain-words status message (shown on the dashboard and in status alerts)."""
    if outcome == "robots_disallowed":
        return f"{domain}'s robots.txt asks bots not to fetch this page, so we don't."
    if outcome == "blocked":
        if error and "bot check" in error:
            return f"{domain} is showing a bot check, so we kept your last good version and will retry later."
        return f"{domain} {error or 'blocked the request'}, so we kept your last good version and will retry later."
    if outcome == "unsafe":
        return error or "That address points to a private network, so it can't be watched."
    return f"Couldn't reach {domain}: {error or 'the request failed'}. We'll try again automatically."


# ---------------------------------------------------------------------------
# Evaluating one watch against one rendered page
# ---------------------------------------------------------------------------

@dataclass
class Eval:
    """The result of evaluating one watch against one fetch."""
    watch: dict
    outcome: str = "unchanged"  # first | unchanged | ignored_minor | ignored_volatile | suspected | changed | error | blocked
    detail: str | None = None
    extracted: extract.Extracted | None = None
    norm: noise.NormalisedText | None = None
    baseline: dict | None = None
    base_norm: noise.NormalisedText | None = None
    size: noise.ChangeSize | None = None
    status: str = "ok"
    status_message: str | None = None
    render: RenderResult | None = None
    snapshot: dict | None = None
    rule_hits: dict = field(default_factory=dict)


def evaluate_text(watch: dict, html: str, rules: list[dict], now: datetime) -> Eval:
    """Extract + normalise one watch's text from a page (no database access)."""
    ev = Eval(watch)
    watch_sel = db.from_json(watch["watch_selectors"], [])
    ignore_sel = db.from_json(watch["ignore_selectors"], [])
    volatile_sel = [r["value"] for r in rules if r.get("kind") == "selector"]
    ev.extracted = extract.extract(html, watch_sel, ignore_sel, bool(watch["ignore_carousels"]), volatile_sel)
    if watch_sel and ev.extracted.missing_selectors:
        ev.outcome = "error"
        ev.status = "error"
        ev.status_message = "The region you picked wasn't found — the page layout may have changed."
        ev.detail = "Picked region not found: " + ", ".join(ev.extracted.missing_selectors)[:300]
        return ev
    ev.norm = noise.normalise_text(ev.extracted.text, effective_sensitivity(watch, now), rules, now.date())
    ev.rule_hits = ev.norm.rule_hits
    return ev


async def latest_snapshot(watch_id: int) -> dict | None:
    return await db.fetch_one("SELECT * FROM snapshots WHERE watch_id = ? ORDER BY id DESC LIMIT 1", (watch_id,))


def read_fetch_html(fetch: dict | None) -> str | None:
    if not fetch or not fetch.get("html_path"):
        return None
    path = settings.data_dir / fetch["html_path"]
    if not path.exists():
        return None
    return gzip.decompress(path.read_bytes()).decode("utf-8", errors="replace")


async def baseline_lines(watch: dict, baseline: dict, rules: list[dict], now: datetime) -> noise.NormalisedText:
    """The baseline version, normalised with TODAY's rules so both sides are treated identically.

    If a selector rule was learned after the baseline was saved, we re-extract the baseline from its
    stored HTML (the rule removes a whole element, which can't be undone from plain text).
    """
    sens = effective_sensitivity(watch, now)
    newer_selector_rule = any(r.get("kind") == "selector" and r.get("learned_at", "") > baseline["created_at"] for r in rules)
    if newer_selector_rule and baseline.get("fetch_id"):
        fetch = await db.fetch_one("SELECT * FROM fetches WHERE id = ?", (baseline["fetch_id"],))
        html = read_fetch_html(fetch)
        if html:
            ev = evaluate_text(watch, html, rules, now)
            if ev.norm is not None:
                return ev.norm
    return noise.normalise_text(baseline["raw_text"], sens, rules, now.date())


async def compare_with_baseline(ev: Eval, rules: list[dict], now: datetime, domain: str) -> None:
    """Decide first / unchanged / ignored_minor / blocked / suspected for one evaluated watch."""
    if ev.outcome == "error" or ev.norm is None:
        return
    ev.baseline = await latest_snapshot(ev.watch["id"])
    if ev.baseline is None:
        ev.outcome = "first"
        ev.detail = "First version saved"
        return
    # Q1: a page whose text suddenly collapses (e.g. a soft bot wall with HTTP 200) is "blocked", not changed.
    base_len, cur_len = len(ev.baseline["raw_text"]), len(ev.norm.raw_text)
    if base_len > 0 and cur_len < 0.2 * base_len and cur_len < 300:
        ev.outcome = "blocked"
        ev.status = "blocked"
        ev.status_message = f"{domain} returned almost none of its usual content, so we kept your last good version and will retry later."
        ev.detail = f"Text shrank from {base_len} to {cur_len} characters"
        return
    ev.base_norm = await baseline_lines(ev.watch, ev.baseline, rules, now)
    if ev.base_norm.norm_lines == ev.norm.norm_lines:
        ev.outcome = "unchanged"
        return
    ev.size = noise.measure_change(ev.base_norm.norm_lines, ev.norm.norm_lines)
    if not noise.is_significant(ev.size, effective_sensitivity(ev.watch, now)):
        ev.outcome = "ignored_minor"
        ev.detail = f"Ignored a tiny change ({ev.size.changed_chars} characters, {ev.size.score:.3%} of the text)"
        return
    ev.outcome = "suspected"


# ---------------------------------------------------------------------------
# Volatility learning (Q3)
# ---------------------------------------------------------------------------

def learn_rules(first: noise.NormalisedText, second: noise.NormalisedText, html_second: str, html_first: str,
                existing: list[dict], whole_len: int) -> list[dict]:
    """Lines that differ between two fetches taken ~10 s apart are volatile; learn a rule for each.

    Two kinds of rule:
      text     — the line's signature (digits -> '#', long words -> '*'); future lines with the same
                 signature are dropped during normalisation.
      selector — the CSS path of the small element the line lives in (e.g. a "tip of the day" box);
                 future extractions remove that element entirely. Only for small elements, so we never
                 learn to ignore a whole section.
    """
    import difflib

    now = db.now_iso()
    known = {(r["kind"], r["value"]) for r in existing}
    new_rules: list[dict] = []
    soups = {"second": extract.learning_soup(html_second), "first": extract.learning_soup(html_first)}
    sm = difflib.SequenceMatcher(None, first.norm_lines, second.norm_lines, autojunk=False)
    volatile: list[tuple[str, str, str]] = []  # (raw, norm, which-fetch)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        volatile += [(first.raw_lines[i], first.norm_lines[i], "first") for i in range(i1, i2)]
        volatile += [(second.raw_lines[j], second.norm_lines[j], "second") for j in range(j1, j2)]

    for raw, norm_line, which in volatile:
        if not norm_line.strip():
            continue
        sig = noise.line_signature(norm_line)
        if len(sig) >= 4 and ("text", sig) not in known:
            new_rules.append({"kind": "text", "value": sig, "sample": raw[:120], "learned_at": now, "hits": 0})
            known.add(("text", sig))
        soup = soups[which]
        el = extract.element_for_line(soup, raw)
        if el is None:
            continue
        el_text = extract.element_text(el)
        if len(el_text) > 400 or len(el_text) > 0.3 * max(1, whole_len):
            continue
        path = extract.css_path(el)
        if not path or ("selector", path) in known:
            continue
        try:
            matches = len(soup.select(path))
        except Exception:
            continue
        if 1 <= matches <= 3:
            new_rules.append({"kind": "selector", "value": path, "sample": raw[:120], "learned_at": now, "hits": 0})
            known.add(("selector", path))
    return new_rules


def merge_rules(existing: list[dict], new: list[dict]) -> list[dict]:
    """Add new rules, keeping at most MAX_RULES (drop the least-used, oldest first)."""
    merged = existing + new
    if len(merged) > MAX_RULES:
        merged.sort(key=lambda r: (r.get("hits", 0), r.get("learned_at", "")), reverse=True)
        merged = merged[:MAX_RULES]
    return merged


def common_change(base: noise.NormalisedText, a: noise.NormalisedText, b: noise.NormalisedText) -> bool:
    """True if at least one added or removed line (vs the baseline) appears in BOTH fetches."""
    sa = noise.measure_change(base.norm_lines, a.norm_lines)
    sb = noise.measure_change(base.norm_lines, b.norm_lines)
    added = Counter(sa.added_lines) & Counter(sb.added_lines)
    removed = Counter(sa.removed_lines) & Counter(sb.removed_lines)
    return bool(added or removed)


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------

async def save_fetch_files(fetch_id: int, target_id: int, render: RenderResult, saved: set[int]) -> None:
    """Write the screenshot and gzipped HTML for a fetch (only once, only when something needs them)."""
    if fetch_id in saved:
        return
    png_rel = f"fetches/{target_id}/{fetch_id}.png"
    html_rel = f"fetches/{target_id}/{fetch_id}.html.gz"
    if render.screenshot:
        data_path(png_rel).write_bytes(render.screenshot)
    data_path(html_rel).write_bytes(gzip.compress(render.html.encode("utf-8"), compresslevel=6))
    await db.execute("UPDATE fetches SET screenshot_path = ?, html_path = ? WHERE id = ?",
                     (png_rel if render.screenshot else None, html_rel, fetch_id))
    saved.add(fetch_id)


async def insert_fetch(target_id: int, render: RenderResult) -> int:
    return await db.execute(
        "INSERT INTO fetches (target_id, fetched_at, http_status, final_url, page_width, page_height, element_boxes, duration_ms) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (target_id, db.now_iso(), render.http_status, render.final_url, render.page_width, render.page_height,
         db.to_json(render.boxes), render.duration_ms),
    )


def keyword_hit(mode: str, keywords: list[str], base_text: str, new_text: str, added: list[str], removed: list[str]) -> str | None:
    """Which keyword (if any) triggers an alert under this watch's keyword mode (bonus feature)."""
    words = [k.strip().strip('"').lower() for k in keywords if k.strip().strip('"')]
    if mode == "off" or not words:
        return None
    base_l, new_l = base_text.lower(), new_text.lower()
    for k in words:
        if mode == "appear" and k in new_l and k not in base_l:
            return k
        if mode == "disappear" and k in base_l and k not in new_l:
            return k
        if mode == "any" and any(k in line.lower() for line in added + removed):
            return k
    return None


async def create_snapshot(ev: Eval, fetch_id: int, render: RenderResult, target_id: int, saved: set[int],
                          is_baseline: bool = False) -> dict:
    """Store a new version: text, hash, diff stats, summary, keyword hit, crop and thumbnail."""
    assert ev.norm is not None
    watch = ev.watch
    content_hash = sha256(ev.norm.norm_text)
    first = ev.baseline is None
    added_lines: list[str] = []
    removed_lines: list[str] = []
    score = 0.0
    if not first and ev.base_norm is not None and not is_baseline:
        diff = differ.diff_lines(ev.base_norm.norm_lines, ev.norm.norm_lines, ev.base_norm.raw_lines, ev.norm.raw_lines)
        preview = differ.changed_lines_preview(diff, limit=50, max_len=400)
        added_lines = [t for sign, t in preview if sign == "+"]
        removed_lines = [t for sign, t in preview if sign == "-"]
        score = diff["stats"]["change_score"]
        added_count, removed_count = diff["stats"]["added"] + diff["stats"]["changed"], diff["stats"]["removed"] + diff["stats"]["changed"]
        summary = summarize.heuristic_summary(added_lines, removed_lines)
    else:
        added_count = removed_count = 0
        summary = "New starting point (regions changed)" if is_baseline else "First version saved"

    hit = None
    if not first and not is_baseline:
        hit = keyword_hit(watch["keyword_mode"], db.from_json(watch["keywords"], []),
                          ev.baseline["raw_text"] if ev.baseline else "", ev.norm.raw_text, added_lines, removed_lines)

    await save_fetch_files(fetch_id, target_id, render, saved)
    snapshot_id = await db.execute(
        "INSERT INTO snapshots (watch_id, fetch_id, content_hash, text, raw_text, created_at, change_summary, "
        "added_lines, removed_lines, change_score, keyword_hit, is_baseline) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (watch["id"], fetch_id, content_hash, ev.norm.norm_text, ev.norm.raw_text, db.now_iso(), summary,
         added_count, removed_count, score, hit, 1 if is_baseline else 0),
    )

    # Crop of the watched region + thumbnail.
    crop_rel = thumb_rel = None
    shot = settings.data_dir / f"fetches/{target_id}/{fetch_id}.png"
    if shot.exists():
        box = visual_diff.union_box(render.boxes, db.from_json(watch["watch_selectors"], []))
        try:
            if box:
                crop_rel = f"crops/{snapshot_id}.png"
                if not visual_diff.save_crop(shot, box, data_path(crop_rel)):
                    crop_rel = None
            thumb_rel = f"thumbs/{snapshot_id}.jpg"
            visual_diff.save_thumbnail(settings.data_dir / (crop_rel or f"fetches/{target_id}/{fetch_id}.png"), data_path(thumb_rel))
        except OSError:
            log.exception("Could not write crop/thumbnail for snapshot %s", snapshot_id)
            thumb_rel = thumb_rel if thumb_rel and (settings.data_dir / thumb_rel).exists() else None
        await db.execute("UPDATE snapshots SET crop_path = ?, thumbnail_path = ? WHERE id = ?", (crop_rel, thumb_rel, snapshot_id))

    snap = await db.fetch_one("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,))
    assert snap is not None
    snap["_added"] = added_lines
    snap["_removed"] = removed_lines
    return snap


# ---------------------------------------------------------------------------
# Number tracking (bonus)
# ---------------------------------------------------------------------------

async def record_number(watch: dict, html: str) -> None:
    """Record one point on every successful check, and fire threshold alerts once per crossing."""
    if not watch.get("number_selector") and not watch.get("number_regex"):
        return
    found = numbers.extract_number(html, watch.get("number_selector"), watch.get("number_regex"))
    if not found:
        return
    value, raw = found
    prev = await db.fetch_one("SELECT value FROM number_points WHERE watch_id = ? ORDER BY id DESC LIMIT 1", (watch["id"],))
    await db.execute("INSERT INTO number_points (watch_id, value, raw, recorded_at) VALUES (?, ?, ?, ?)",
                     (watch["id"], value, raw, db.now_iso()))
    if prev is None:
        return
    old = prev["value"]
    th = db.from_json(watch.get("number_thresholds"), {})
    if th.get("below") is not None and old >= th["below"] > value:
        await alerts.on_threshold(watch, "below", value, raw)
    if th.get("above") is not None and old <= th["above"] < value:
        await alerts.on_threshold(watch, "above", value, raw)
    if th.get("change_pct") and old and abs(value - old) / abs(old) * 100 >= th["change_pct"]:
        await alerts.on_threshold(watch, "change_pct", value, raw)


# ---------------------------------------------------------------------------
# Failure handling (Q1)
# ---------------------------------------------------------------------------

async def apply_failure(target: dict, due: list[dict], outcome: str, error: str | None, attempt: int,
                        started_iso: str, duration_ms: int, retry_after: float | None = None) -> None:
    """Final failure of a check: mark error/blocked, back off, maybe send ONE status alert. Never a change."""
    domain = display_domain(target["url"])
    status = "blocked" if outcome in ("blocked", "robots_disallowed") else "error"
    failures = target["consecutive_failures"] + 1
    all_watches = await db.fetch_all("SELECT * FROM watches WHERE target_id = ? AND paused = 0", (target["id"],))
    base = effective_interval_s(all_watches or due)
    # Exponential failure backoff: interval × 2, 4, 8 (capped) — or longer if the site asked (Retry-After).
    wait = base * min(2 ** failures, 8) if outcome != "robots_disallowed" else base
    if retry_after:
        wait = max(wait, retry_after)
    next_at = iso_in(jittered(wait))
    message = friendly_failure(domain, "unsafe" if outcome == "unsafe" else outcome, error)
    log_outcome = "error" if outcome == "unsafe" else outcome
    await db.execute(
        "UPDATE targets SET status = ?, consecutive_failures = ?, last_error = ?, next_fetch_at = ?, last_fetched_at = ? WHERE id = ?",
        (status, failures, error, next_at, db.now_iso(), target["id"]),
    )
    now_iso = db.now_iso()
    for w in due:
        changed_status = w["status"] != status
        await db.execute(
            "UPDATE watches SET status = ?, status_message = ?, last_checked_at = ?, next_due_at = ? WHERE id = ?",
            (status, message, now_iso, next_at, w["id"]),
        )
        await log_check(target["id"], w["id"], log_outcome, attempt, message, started_iso, duration_ms)
        if changed_status:
            bus.publish(w["user_id"], "status_change", {"watch_id": w["id"], "status": status, "message": message})
        bus.publish(w["user_id"], "check_finished", {
            "watch_id": w["id"], "outcome": log_outcome, "status": status, "last_checked_at": now_iso, "next_due_at": next_at})
        if failures >= STATUS_ALERT_AFTER:
            await alerts.on_status(w, status, message)


async def on_give_up(target_id: int, attempt: int, reason: str) -> None:
    """Called by the queue when a whole job hit its safety timeout."""
    target = await db.fetch_one("SELECT * FROM targets WHERE id = ?", (target_id,))
    if not target:
        return
    due = await db.fetch_all("SELECT * FROM watches WHERE target_id = ? AND paused = 0", (target_id,))
    await apply_failure(target, due, "timeout", reason, attempt, db.now_iso(), 0)
    await db.execute("UPDATE targets SET running_since = NULL WHERE id = ?", (target_id,))


# ---------------------------------------------------------------------------
# The main entry point
# ---------------------------------------------------------------------------

async def conditional_unchanged(target: dict) -> bool:
    """Cheap pre-check: ask the server if the page changed since our last render (HTTP 304)."""
    headers = {"User-Agent": politeness.user_agent}
    if target["etag"]:
        headers["If-None-Match"] = target["etag"]
    if target["last_modified"]:
        headers["If-Modified-Since"] = target["last_modified"]
    try:
        async with politeness.slot(target["url"]):
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                response = await client.get(target["url"], headers=headers)
    except httpx.HTTPError:
        return False
    return response.status_code == 304


def selectors_needed(watches: list[dict]) -> list[str]:
    """Every selector any watch on this target needs a bounding box for (crops, number preview)."""
    out: list[str] = []
    for w in watches:
        out += db.from_json(w["watch_selectors"], [])
        if w.get("number_selector"):
            out.append(w["number_selector"])
    return sorted(set(out))


async def check_target(target_id: int, attempt: int, is_last: bool, priority: int) -> AttemptResult:
    """One attempt at checking a target. Called by a jobqueue worker."""
    target = await db.fetch_one("SELECT * FROM targets WHERE id = ?", (target_id,))
    if target is None:
        return AttemptResult()
    watches = await db.fetch_all("SELECT * FROM watches WHERE target_id = ? AND paused = 0", (target_id,))
    if not watches:
        return AttemptResult()
    now = utcnow()
    due = watches if priority == 0 else [w for w in watches if is_due(w, now)]
    if not due:
        # Fired early because of jitter: evaluate the watch(es) closest to due rather than wasting the fetch.
        soonest = min(w["next_due_at"] or "" for w in watches)
        due = [w for w in watches if (w["next_due_at"] or "") == soonest]

    started_iso = db.now_iso()
    started = time.monotonic()
    await db.execute("UPDATE targets SET running_since = ? WHERE id = ?", (started_iso, target_id))
    bus.publish_many({w["user_id"] for w in due}, "check_started", {"watch_ids": [w["id"] for w in due]})
    try:
        return await _check(target, watches, due, attempt, is_last, priority, started_iso, started)
    finally:
        await db.execute("UPDATE targets SET running_since = NULL WHERE id = ?", (target_id,))
        await trim_check_log(target_id)


async def _check(target: dict, watches: list[dict], due: list[dict], attempt: int, is_last: bool, priority: int,
                 started_iso: str, started: float) -> AttemptResult:
    url = target["url"]
    domain = display_domain(url)
    elapsed = lambda: int((time.monotonic() - started) * 1000)  # noqa: E731

    # 2. Public-only guard (re-checked every time) and robots.txt.
    try:
        await security.check_url_is_public(url)
    except security.UnsafeURL as exc:
        await apply_failure(target, due, "unsafe", str(exc), attempt, started_iso, elapsed())
        return AttemptResult()
    if not await politeness.robots_allows(url):
        await apply_failure(target, due, "robots_disallowed", "Disallowed by robots.txt", attempt, started_iso, elapsed())
        return AttemptResult()

    # 3. Conditional pre-check (only for static pages where the HTML holds the content).
    if priority != 0 and target["static_html"] and (target["etag"] or target["last_modified"]):
        if await conditional_unchanged(target):
            await finish_not_modified(target, watches, due, started_iso, elapsed())
            return AttemptResult()

    # 4. Render once for everyone.
    selectors = selectors_needed(watches)
    async with politeness.slot(url):
        render = await fetcher.render(url, selectors)

    # 5. Classify.
    if not render.ok:
        outcome = "timeout" if render.outcome == "timeout" else render.outcome
        if render.retry_after:
            politeness.defer(url, render.retry_after)
        if render.retryable and not is_last and not (render.retry_after and render.retry_after > 120):
            await log_check(target["id"], None, outcome, attempt, f"Attempt {attempt} failed: {render.error}. Retrying.", started_iso, elapsed())
            return AttemptResult(retryable=True, retry_after=render.retry_after)
        await apply_failure(target, due, outcome, render.error, attempt, started_iso, elapsed(), render.retry_after)
        return AttemptResult()

    await handle_success(target, watches, due, render, attempt, started_iso, started)
    return AttemptResult()


async def finish_not_modified(target: dict, watches: list[dict], due: list[dict], started_iso: str, duration_ms: int) -> None:
    """Server said 304 Not Modified: everyone's page is unchanged; no browser needed."""
    now_iso = db.now_iso()
    next_fetch = iso_in(jittered(effective_interval_s(watches)))
    await db.execute("UPDATE targets SET last_fetched_at = ?, next_fetch_at = ?, status = 'ok', consecutive_failures = 0 WHERE id = ?",
                     (now_iso, next_fetch, target["id"]))
    for w in due:
        next_due = iso_in(settings.minutes_to_seconds(w["interval_minutes"]))
        await db.execute("UPDATE watches SET last_checked_at = ?, next_due_at = ?, status = 'ok', status_message = NULL WHERE id = ?",
                         (now_iso, next_due, w["id"]))
        await log_check(target["id"], w["id"], "not_modified", 1, "Server said nothing changed (HTTP 304); skipped the browser", started_iso, duration_ms)
        bus.publish(w["user_id"], "check_finished", {"watch_id": w["id"], "outcome": "not_modified", "status": "ok",
                                                     "last_checked_at": now_iso, "next_due_at": next_due})


def detect_static(render: RenderResult) -> bool:
    """Is the visible text already in the server's HTML (no JavaScript needed)? Then 304s can be trusted."""
    if not render.raw_html:
        return False
    raw_text = extract.visible_text_of_raw_html(render.raw_html)
    rendered = extract.extract(render.html, [], [], True).text
    lines = [line for line in rendered.split("\n") if len(line) >= 20][:200]
    if len(lines) < 3:
        return False
    present = sum(1 for line in lines if line in raw_text)
    return present / len(lines) >= 0.8


async def handle_success(target: dict, watches: list[dict], due: list[dict], render: RenderResult, attempt: int,
                         started_iso: str, started: float) -> None:
    """Steps 6–8: evaluate every due watch from this render, confirm, learn, snapshot, alert."""
    now = utcnow()
    domain = display_domain(target["url"])
    rules: list[dict] = db.from_json(target["volatile_rules"], [])
    was_failing = target["consecutive_failures"] >= STATUS_ALERT_AFTER
    fetch_id = await insert_fetch(target["id"], render)
    saved: set[int] = set()
    first_fetch = target["last_fetched_at"] is None

    # 6. Evaluate each due watch from the same render.
    evals = []
    for w in due:
        ev = evaluate_text(w, render.html, rules, now)
        ev.render = render
        await compare_with_baseline(ev, rules, now, domain)
        evals.append(ev)

    # 7. Confirmation re-fetch + volatility learning, only when something looks changed.
    suspected = [ev for ev in evals if ev.outcome == "suspected"]
    confirm_fetch_id = fetch_id
    confirm_render = render
    if suspected and settings.confirm_refetch:
        async with politeness.slot(target["url"]):
            second = await fetcher.render(target["url"], selectors_needed(watches))
        if second.ok:
            confirm_render = second
            confirm_fetch_id = await insert_fetch(target["id"], second)
            whole_len = len(extract.extract(render.html, [], [], True).text)
            new_rules: list[dict] = []
            for ev in suspected:
                ev2 = evaluate_text(ev.watch, second.html, rules, now)
                if ev2.norm is not None and ev.norm is not None and ev2.norm.norm_lines != ev.norm.norm_lines:
                    new_rules += learn_rules(ev.norm, ev2.norm, second.html, render.html, rules + new_rules, whole_len)
            if new_rules:
                rules = merge_rules(rules, new_rules)
                await db.execute("UPDATE targets SET volatile_rules = ? WHERE id = ?", (db.to_json(rules), target["id"]))
            # Re-evaluate both fetches with the (possibly) new rules; keep only changes present in both.
            for ev in suspected:
                e1 = evaluate_text(ev.watch, render.html, rules, now)
                e2 = evaluate_text(ev.watch, second.html, rules, now)
                if e1.norm is None or e2.norm is None or ev.baseline is None:
                    continue
                base = await baseline_lines(ev.watch, ev.baseline, rules, now)
                ev.base_norm = base
                ev.norm, ev.extracted, ev.render = e2.norm, e2.extracted, second
                ev.rule_hits = e2.rule_hits
                if base.norm_lines == e2.norm.norm_lines or not common_change(base, e1.norm, e2.norm):
                    ev.outcome = "ignored_volatile"
                    ev.detail = (f"Ignored: this part changes on every load — learned {len(new_rules)} new rule"
                                 f"{'s' if len(new_rules) != 1 else ''}")
                    continue
                ev.size = noise.measure_change(base.norm_lines, e2.norm.norm_lines)
                if not noise.is_significant(ev.size, effective_sensitivity(ev.watch, now)):
                    ev.outcome = "ignored_minor"
                    ev.detail = f"Ignored a tiny change ({ev.size.changed_chars} characters)"
                    continue
                ev.outcome = "suspected"
        # If the confirmation fetch failed we accept the first fetch's verdict (no rules learned).

    # Count rule hits (shown in the UI next to each learned rule).
    hit_total: Counter = Counter()
    for ev in evals:
        hit_total.update(ev.rule_hits)
    if hit_total:
        for r in rules:
            if r.get("kind") == "text" and r["value"] in hit_total:
                r["hits"] = r.get("hits", 0) + hit_total[r["value"]]
        await db.execute("UPDATE targets SET volatile_rules = ? WHERE id = ?", (db.to_json(rules), target["id"]))

    # 8. Snapshots, alerts, events.
    now_iso = db.now_iso()
    for ev in evals:
        w = ev.watch
        snap_render = ev.render or render
        snap_fetch = confirm_fetch_id if snap_render is confirm_render else fetch_id
        outcome_for_log = ev.outcome
        snapshot = None
        if ev.outcome in ("first", "suspected"):
            snapshot = await create_snapshot(ev, snap_fetch, snap_render, target["id"], saved)
            ev.snapshot = snapshot
            outcome_for_log = "changed"
            if ev.outcome == "suspected":
                ev.detail = snapshot["change_summary"]
        if ev.outcome == "error":
            outcome_for_log = "error"

        updates = {
            "last_checked_at": now_iso,
            "next_due_at": iso_in(settings.minutes_to_seconds(w["interval_minutes"])),
            "status": ev.status,
            "status_message": ev.status_message,
        }
        if not w["name"] and render.title:
            updates["name"] = render.title[:120]
        if snapshot is not None:
            updates["last_content_hash"] = snapshot["content_hash"]
            if ev.outcome == "suspected":
                updates["last_changed_at"] = now_iso
        sets = ", ".join(f"{k} = ?" for k in updates)
        await db.execute(f"UPDATE watches SET {sets} WHERE id = ?", (*updates.values(), w["id"]))

        await log_check(target["id"], w["id"], outcome_for_log, attempt, ev.detail, started_iso, int((time.monotonic() - started) * 1000))

        if ev.status == "ok":
            await record_number(w, snap_render.html)

        if w["status"] != ev.status:
            bus.publish(w["user_id"], "status_change", {"watch_id": w["id"], "status": ev.status, "message": ev.status_message})
        if ev.status == "error" and ev.status_message and "region" in ev.status_message:
            await alerts.on_status(w, "region_missing", ev.status_message)

        if snapshot is not None and ev.outcome == "suspected":
            prev_id = ev.baseline["id"] if ev.baseline else None
            await after_change(w, snapshot, prev_id, ev)
        bus.publish(w["user_id"], "check_finished", {
            "watch_id": w["id"], "outcome": outcome_for_log, "status": ev.status,
            "last_checked_at": now_iso, "next_due_at": updates["next_due_at"]})

    if first_fetch:
        await save_fetch_files(fetch_id, target["id"], render, saved)

    # Target bookkeeping.
    await db.execute(
        "UPDATE targets SET status = 'ok', consecutive_failures = 0, last_error = NULL, last_fetched_at = ?, "
        "next_fetch_at = ?, last_http_status = ?, etag = ?, last_modified = ?, title = ?, static_html = ? WHERE id = ?",
        (now_iso, iso_in(jittered(effective_interval_s(watches))), render.http_status, render.headers.get("etag"),
         render.headers.get("last-modified"), render.title[:200] if render.title else None,
         1 if detect_static(render) else 0, target["id"]),
    )
    if was_failing:
        for w in due:
            await alerts.on_status(w, "ok", f"{domain} is reachable again. Checks are back to normal.")


async def after_change(watch: dict, snapshot: dict, previous_id: int | None, ev: Eval) -> None:
    """Flapping guard, live event and alerts for one detected change."""
    now = utcnow()
    # Flapping: too many changes in 6 hours, or A→B→A→B oscillation.
    recent = await db.fetch_all(
        "SELECT content_hash FROM snapshots WHERE watch_id = ? AND id < ? ORDER BY id DESC LIMIT 3", (watch["id"], snapshot["id"]))
    since = (now - timedelta(hours=FLAP_WINDOW_H)).isoformat()
    count = await db.fetch_value(
        "SELECT COUNT(*) FROM snapshots WHERE watch_id = ? AND is_baseline = 0 AND created_at >= ? AND change_summary != 'First version saved'",
        (watch["id"], since))
    oscillating = noise.is_oscillating(snapshot["content_hash"], [r["content_hash"] for r in recent])
    flapping_until = db.parse_iso(watch.get("flapping_until"))
    if (count >= FLAP_COUNT or oscillating) and not (flapping_until and flapping_until > now):
        until = (now + timedelta(hours=24)).isoformat()
        await db.execute("UPDATE watches SET flapping_until = ? WHERE id = ?", (until, watch["id"]))
        watch = {**watch, "flapping_until": until}
        await alerts.on_flapping(watch)

    bus.publish(watch["user_id"], "change", {
        "watch_id": watch["id"], "snapshot_id": snapshot["id"], "previous_snapshot_id": previous_id,
        "summary": snapshot["change_summary"], "added": snapshot["added_lines"], "removed": snapshot["removed_lines"],
        "name": watch["name"] or display_domain((await db.fetch_one("SELECT url FROM targets WHERE id = ?", (watch["target_id"],)) or {"url": ""})["url"]),
    })
    # Keyword mode filters alerts only — the snapshot is always saved so history stays complete.
    if watch["keyword_mode"] != "off" and db.from_json(watch["keywords"], []) and not snapshot["keyword_hit"]:
        return
    preview = list(zip(["+"] * len(snapshot["_added"]), snapshot["_added"])) + list(zip(["-"] * len(snapshot["_removed"]), snapshot["_removed"]))
    await alerts.on_change(watch, snapshot, previous_id, preview[:5])


async def rebaseline(watch_id: int) -> dict | None:
    """After the user changes regions: compute the new text from the latest stored page and save it as a
    'New starting point' snapshot. No alert, because nothing on the page changed — only what we look at."""
    watch = await db.fetch_one("SELECT * FROM watches WHERE id = ?", (watch_id,))
    if not watch:
        return None
    target = await db.fetch_one("SELECT * FROM targets WHERE id = ?", (watch["target_id"],))
    fetch = await db.fetch_one(
        "SELECT * FROM fetches WHERE target_id = ? AND html_path IS NOT NULL ORDER BY id DESC LIMIT 1", (watch["target_id"],))
    html = read_fetch_html(fetch)
    if not html or not target or not fetch:
        return None
    rules = db.from_json(target["volatile_rules"], [])
    now = utcnow()
    ev = evaluate_text(watch, html, rules, now)
    if ev.norm is None:
        return None
    ev.baseline = await latest_snapshot(watch_id)
    render = RenderResult("ok", target["url"], html=html, boxes=db.from_json(fetch["element_boxes"], {}))
    snap = await create_snapshot(ev, fetch["id"], render, target["id"], {fetch["id"]}, is_baseline=True)
    await db.execute("UPDATE watches SET last_content_hash = ?, status = 'ok', status_message = NULL WHERE id = ?",
                     (snap["content_hash"], watch_id))
    return snap
