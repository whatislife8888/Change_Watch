"""
alerts.py — telling people about changes: email, Telegram and Discord (requirement 7).

Who uses it: checker.py (on_change, on_status, on_flapping, on_threshold), digest.py, routes/settings.py.
Depends on: smtplib (run in a thread) or Resend's HTTP API for email, httpx for Telegram/Discord,
visual_diff (the highlighted screenshot attached to emails), db.

No duplicates — the important idea:
  Before sending, we INSERT a row into `alerts` with
      dedupe_key = sha256("{kind}:{watch_id}:{content_hash}:{channel}")
  The column is UNIQUE, so the database itself refuses a second row with the same key. We only send
  if our insert succeeded. A retried job, a restart halfway through, or two workers racing on the same
  change can therefore never send the same alert twice ("idempotent").

Each channel is delivered in its own background task with up to 3 retries (2 s, 10 s, 30 s); one
channel failing never blocks the others, and a channel that isn't configured is recorded as failed with
a clear reason instead of crashing anything.
"""
import asyncio
import base64
import hashlib
import html
import io
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import make_msgid
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from PIL import Image

from . import db, visual_diff
from .config import settings
from .urlnorm import display_domain

log = logging.getLogger("changewatch.alerts")

RETRY_DELAYS = [2, 10, 30]
CHANNELS = ("email", "telegram", "discord")
DISCORD_HOSTS = {"discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com"}
_background: set[asyncio.Task] = set()


# ---------------------------------------------------------------------------
# Message building
# ---------------------------------------------------------------------------

@dataclass
class AlertMessage:
    kind: str                      # change | status | flapping | threshold | test
    page_name: str
    page_url: str
    headline: str                  # first line, e.g. "VIT News changed"
    summary: str                   # the one-line summary or status explanation
    link: str                      # absolute link into the app (compare view or page)
    when: str                      # local time in the user's timezone
    added: int = 0
    removed: int = 0
    preview: list[tuple[str, str]] = field(default_factory=list)  # ("+"|"-", line)
    diff_ids: tuple[int, int] | None = None  # (a, b) for the email image

    def subject(self) -> str:
        return f"{self.headline}: {self.summary}"[:150]


def dedupe_key(material: str) -> str:
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def local_time(user: dict, when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    try:
        tz = ZoneInfo(user.get("timezone") or "Asia/Kolkata")
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")
    return when.astimezone(tz).strftime("%d %b %Y, %I:%M %p").lstrip("0") + f" ({tz.key})"


def app_link(path: str) -> str:
    return settings.base_url.rstrip("/") + path


def render_text(msg: AlertMessage) -> str:
    lines = [msg.headline, msg.summary, "", f"Page: {msg.page_name}", f"Address: {msg.page_url}", f"When: {msg.when}"]
    if msg.kind == "change":
        lines.append(f"Lines: +{msg.added} / -{msg.removed}")
    if msg.preview:
        lines += ["", "What changed:"] + [f"{sign} {text}" for sign, text in msg.preview]
    lines += ["", f"Open in ChangeWatch: {msg.link}", "", "You get this because you watch this page on ChangeWatch."]
    return "\n".join(lines)


def render_email_html(msg: AlertMessage, image_cid: str | None) -> str:
    """A simple, robust HTML email (tables + inline styles, because email clients ignore most CSS)."""
    e = html.escape
    rows = "".join(
        f'<tr><td style="padding:6px 10px;font:13px/1.5 Menlo,monospace;background:{"#e8f5ee" if s == "+" else "#fbe9ee"};'
        f'color:#141917;border-radius:4px"><b style="color:{"#1A7550" if s == "+" else "#B8163F"}">{s}</b> {e(t)}</td></tr>'
        f'<tr><td style="height:4px"></td></tr>'
        for s, t in msg.preview)
    stats = (f'<p style="margin:0 0 16px;color:#4F5754;font:14px/1.5 Helvetica,Arial,sans-serif">'
             f'<span style="color:#1A7550">+{msg.added}</span> / <span style="color:#B8163F">&minus;{msg.removed}</span> lines</p>'
             if msg.kind == "change" else "")
    image = (f'<img src="cid:{image_cid[1:-1]}" width="560" alt="Screenshot with the changed areas outlined" '
             f'style="display:block;width:100%;max-width:560px;border:1px solid #d6d9d4;border-radius:8px;margin:20px 0">'
             if image_cid else "")
    return f"""<!doctype html><html><body style="margin:0;background:#E9EAE6;padding:24px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:16px;padding:32px">
<tr><td>
<p style="margin:0 0 6px;font:14px Helvetica,Arial,sans-serif;color:#4F5754">ChangeWatch</p>
<h1 style="margin:0 0 12px;font:400 26px/1.25 Georgia,serif;color:#141917">{e(msg.headline)}</h1>
<p style="margin:0 0 12px;font:16px/1.55 Helvetica,Arial,sans-serif;color:#141917">{e(msg.summary)}</p>
{stats}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>
{image}
<p style="margin:24px 0"><a href="{e(msg.link)}" style="display:inline-block;background:#2340C8;color:#ffffff;text-decoration:none;
font:600 15px Helvetica,Arial,sans-serif;padding:12px 22px;border-radius:999px">{'Compare versions' if msg.kind == 'change' else 'Open in ChangeWatch'}</a></p>
<p style="margin:0;font:13px/1.5 Helvetica,Arial,sans-serif;color:#6C7470">{e(msg.page_name)} &middot; <a href="{e(msg.page_url)}" style="color:#2340C8">{e(display_domain(msg.page_url))}</a><br>{e(msg.when)}</p>
</td></tr></table>
<p style="font:12px Helvetica,Arial,sans-serif;color:#6C7470">You get this because you watch this page on ChangeWatch.</p>
</td></tr></table></body></html>"""


def render_telegram(msg: AlertMessage) -> str:
    """Telegram's HTML mode supports only a few tags; everything else must be escaped. Max 4096 chars."""
    e = html.escape
    parts = [f"<b>{e(msg.headline)}</b>", e(msg.summary)]
    if msg.kind == "change":
        parts.append(f"+{msg.added} / −{msg.removed} lines")
    if msg.preview:
        parts.append("\n".join(f"{'➕' if s == '+' else '➖'} {e(t)}" for s, t in msg.preview))
    parts.append(f'<a href="{e(msg.link)}">Open in ChangeWatch</a>  ·  {e(msg.when)}')
    text = "\n\n".join(parts)
    return text if len(text) <= 4096 else text[:4090] + "…"


def render_discord(msg: AlertMessage) -> dict:
    colour = {"change": 0xEFA98C, "status": 0xF4B860, "flapping": 0xF4B860, "threshold": 0x5B78F6, "test": 0xBFF7D8}
    preview = "\n".join(f"{'+' if s == '+' else '-'} {t}" for s, t in msg.preview)
    description = msg.summary + (f"\n```diff\n{preview[:3500]}\n```" if preview else "")
    embed = {
        "title": msg.headline[:256],
        "url": msg.link,
        "description": description[:4096],
        "color": colour.get(msg.kind, 0xEFA98C),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": f"ChangeWatch · {display_domain(msg.page_url)}"},
        "fields": [],
    }
    if msg.kind == "change":
        embed["fields"] = [{"name": "Added", "value": f"+{msg.added} lines", "inline": True},
                           {"name": "Removed", "value": f"−{msg.removed} lines", "inline": True}]
    return {"username": "ChangeWatch", "embeds": [embed]}


# ---------------------------------------------------------------------------
# Senders
# ---------------------------------------------------------------------------

class NotConfigured(Exception):
    """The channel has no credentials. Recorded as 'failed' with this message; never retried."""


def channel_ready(channel: str, user: dict) -> str | None:
    """None if the channel can send for this user, else a human reason why not."""
    if channel == "email":
        return None if settings.email_configured else "Email isn't set up on this server (SMTP or Resend credentials missing)."
    if channel == "telegram":
        if not (user.get("telegram_bot_token") or settings.telegram_bot_token):
            return "Telegram isn't set up: no bot token."
        if not user.get("telegram_chat_id"):
            return "Telegram isn't set up: add your chat id in Settings."
        return None
    if channel == "discord":
        url = user.get("discord_webhook_url")
        if not url:
            return "Discord isn't set up: add a webhook URL in Settings."
        return None if valid_discord_webhook(url) else "That Discord webhook URL isn't valid."
    return "Unknown channel."


def valid_discord_webhook(url: str) -> bool:
    """Only real Discord webhook URLs. Why: we POST to this URL from our server, so an arbitrary URL would be
    an SSRF hole (e.g. http://169.254.169.254/)."""
    parts = urlsplit(url)
    return parts.scheme == "https" and (parts.hostname or "") in DISCORD_HOSTS and parts.path.startswith("/api/webhooks/")


def email_image(diff_ids: tuple[int, int] | None) -> bytes | None:
    """The highlighted 'after' screenshot, cropped to the top 1600 px and scaled to 600 px wide (small email)."""
    if not diff_ids:
        return None
    path = visual_diff.diff_image_path(*diff_ids)
    if not path.exists():
        return None
    with Image.open(path) as img:
        img = img.convert("RGB").crop((0, 0, img.width, min(img.height, 1600)))
        img = img.resize((600, max(1, int(img.height * 600 / img.width))))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=80)
        return out.getvalue()


def _smtp_send(message: EmailMessage) -> None:
    context = ssl.create_default_context()
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=20) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls(context=context)
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)


async def send_email(to: str, msg: AlertMessage) -> None:
    if not settings.email_configured:
        raise NotConfigured(channel_ready("email", {}) or "")
    image = await asyncio.to_thread(email_image, msg.diff_ids)
    sender = settings.smtp_from or settings.smtp_user or "ChangeWatch <alerts@changewatch.app>"
    if settings.email_provider == "resend":
        cid = "diff-image"
        payload = {
            "from": sender, "to": [to], "subject": msg.subject(), "text": render_text(msg),
            "html": render_email_html(msg, f"<{cid}>" if image else None),
        }
        if image:
            payload["attachments"] = [{"filename": "changes.jpg", "content": base64.b64encode(image).decode(), "content_id": cid}]
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post("https://api.resend.com/emails", json=payload,
                                  headers={"Authorization": f"Bearer {settings.resend_api_key}"})
        if r.status_code >= 300:
            raise RuntimeError(f"Resend said {r.status_code}: {r.text[:200]}")
        return
    message = EmailMessage()
    message["Subject"] = msg.subject()
    message["From"] = sender
    message["To"] = to
    message.set_content(render_text(msg))
    cid = make_msgid(domain="changewatch") if image else None
    message.add_alternative(render_email_html(msg, cid), subtype="html")
    if image and cid:
        message.get_payload()[1].add_related(image, maintype="image", subtype="jpeg", cid=cid)
    await asyncio.to_thread(_smtp_send, message)


async def send_telegram(user: dict, msg: AlertMessage) -> None:
    token = user.get("telegram_bot_token") or settings.telegram_bot_token
    if not token or not user.get("telegram_chat_id"):
        raise NotConfigured(channel_ready("telegram", user) or "")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
            "chat_id": user["telegram_chat_id"], "text": render_telegram(msg),
            "parse_mode": "HTML", "disable_web_page_preview": True,
        })
    if r.status_code >= 300:
        description = r.json().get("description", r.text[:200]) if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]
        if r.status_code in (400, 401, 403, 404):
            raise NotConfigured(f"Telegram refused the message: {description}")
        raise RuntimeError(f"Telegram said {r.status_code}: {description}")


async def send_discord(user: dict, msg: AlertMessage) -> None:
    url = user.get("discord_webhook_url")
    if not url or not valid_discord_webhook(url):
        raise NotConfigured(channel_ready("discord", user) or "")
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        r = await client.post(url, json=render_discord(msg))
    if r.status_code >= 300:
        if r.status_code in (400, 401, 403, 404):
            raise NotConfigured(f"Discord refused the message (HTTP {r.status_code}). Check the webhook URL.")
        raise RuntimeError(f"Discord said {r.status_code}")


async def send_via(channel: str, user: dict, msg: AlertMessage) -> None:
    if channel == "email":
        await send_email(user["email"], msg)
    elif channel == "telegram":
        await send_telegram(user, msg)
    elif channel == "discord":
        await send_discord(user, msg)


# ---------------------------------------------------------------------------
# Claim (dedupe) + deliver (retries)
# ---------------------------------------------------------------------------

async def claim(user: dict, watch_id: int | None, snapshot_id: int | None, kind: str, channel: str,
                material: str, status: str = "queued", payload: dict | None = None) -> int | None:
    """Insert the alerts row first. Returns its id, or None if this exact alert already exists."""
    return await db.insert_unique(
        "INSERT INTO alerts (watch_id, snapshot_id, user_id, kind, channel, dedupe_key, status, created_at, payload) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (watch_id, snapshot_id, user["id"], kind, channel, dedupe_key(material), status, db.now_iso(),
         db.to_json(payload) if payload else None),
    )


async def deliver(alert_id: int, channel: str, user: dict, msg: AlertMessage) -> bool:
    """Send with up to 3 retries. Updates the alerts row with the outcome. Returns True if sent."""
    error = None
    for attempt in range(1, len(RETRY_DELAYS) + 2):
        try:
            await send_via(channel, user, msg)
            await db.execute("UPDATE alerts SET status = 'sent', sent_at = ?, attempts = ?, error = NULL WHERE id = ?",
                             (db.now_iso(), attempt, alert_id))
            return True
        except NotConfigured as exc:
            error = str(exc)
            break
        except Exception as exc:  # network errors, SMTP errors, 5xx...
            error = f"{type(exc).__name__}: {exc}"[:300]
            log.warning("Alert %s via %s failed (attempt %s): %s", alert_id, channel, attempt, error)
            if attempt <= len(RETRY_DELAYS):
                await asyncio.sleep(RETRY_DELAYS[attempt - 1])
    await db.execute("UPDATE alerts SET status = 'failed', attempts = attempts + 1, error = ? WHERE id = ?", (error, alert_id))
    return False


def spawn(coro) -> None:
    """Run delivery in the background so a slow SMTP server never holds up a check."""
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


async def dispatch(user: dict, watch: dict, kind: str, material_base: str, msg: AlertMessage,
                   snapshot_id: int | None = None, extra_payload: dict | None = None) -> int:
    """Claim + deliver on every channel the watch has enabled. Returns how many new alerts were claimed."""
    claimed = 0
    for channel in CHANNELS:
        if not watch.get(f"alert_{channel}"):
            continue
        alert_id = await claim(user, watch["id"], snapshot_id, kind, channel, f"{material_base}:{channel}",
                               payload={**(extra_payload or {}), "subject": msg.subject()})
        if alert_id is None:
            continue  # already handled — this is the dedupe at work
        claimed += 1
        reason = channel_ready(channel, user)
        if reason:
            await db.execute("UPDATE alerts SET status = 'failed', error = ? WHERE id = ?", (reason, alert_id))
            continue
        spawn(deliver(alert_id, channel, user, msg))
    return claimed


async def _context(watch: dict) -> tuple[dict, dict] | None:
    user = await db.fetch_one("SELECT * FROM users WHERE id = ?", (watch["user_id"],))
    target = await db.fetch_one("SELECT url FROM targets WHERE id = ?", (watch["target_id"],))
    if not user or not target:
        return None
    return user, target


# ---------------------------------------------------------------------------
# Entry points used by the checker
# ---------------------------------------------------------------------------

async def on_change(watch: dict, snapshot: dict, previous_snapshot_id: int | None, preview: list[tuple[str, str]]) -> None:
    """A real change: alert every enabled channel once (or queue it for the daily digest)."""
    ctx = await _context(watch)
    if not ctx:
        return
    user, target = ctx
    name = watch["name"] or display_domain(target["url"])
    link = app_link(f"/pages/{watch['id']}/compare?a={previous_snapshot_id}&b={snapshot['id']}") if previous_snapshot_id else app_link(f"/pages/{watch['id']}")
    msg = AlertMessage(
        kind="change", page_name=name, page_url=target["url"], headline=f"{name} changed",
        summary=snapshot.get("ai_summary") or snapshot["change_summary"] or "The page changed.",
        link=link, when=local_time(user), added=snapshot["added_lines"], removed=snapshot["removed_lines"],
        preview=preview[:5], diff_ids=(previous_snapshot_id, snapshot["id"]) if previous_snapshot_id else None,
    )
    material = f"change:{watch['id']}:{snapshot['content_hash']}"
    if user["digest_mode"] == "daily":
        await claim(user, watch["id"], snapshot["id"], "change", "digest", f"{material}:digest", status="queued_digest",
                    payload={"name": name, "summary": msg.summary, "link": link, "added": msg.added, "removed": msg.removed,
                             "url": target["url"], "at": db.now_iso()})
        return
    if msg.diff_ids and watch.get("alert_email"):
        # Prepare the highlighted screenshot for the email (cached on disk; also used by the Compare page).
        await _prepare_diff_image(msg.diff_ids)
    await dispatch(user, watch, "change", material, msg, snapshot["id"])


async def _prepare_diff_image(diff_ids: tuple[int, int]) -> None:
    a = await db.fetch_one("SELECT f.screenshot_path FROM snapshots s JOIN fetches f ON f.id = s.fetch_id WHERE s.id = ?", (diff_ids[0],))
    b = await db.fetch_one("SELECT f.screenshot_path FROM snapshots s JOIN fetches f ON f.id = s.fetch_id WHERE s.id = ?", (diff_ids[1],))
    if not a or not b or not a["screenshot_path"] or not b["screenshot_path"]:
        return
    pa, pb = settings.data_dir / a["screenshot_path"], settings.data_dir / b["screenshot_path"]
    if pa.exists() and pb.exists():
        try:
            await asyncio.to_thread(visual_diff.cached_compare, diff_ids[0], diff_ids[1], pa, pb)
        except Exception:
            log.exception("Could not build the diff image for %s", diff_ids)


async def on_status(watch: dict, status: str, message: str) -> None:
    """ONE "we can't reach this page" alert per watch, status and day; ONE "back to normal" on recovery."""
    ctx = await _context(watch)
    if not ctx:
        return
    user, target = ctx
    name = watch["name"] or display_domain(target["url"])
    today = datetime.now(timezone.utc).date().isoformat()
    if status == "ok":
        last = await db.fetch_one(
            "SELECT payload FROM alerts WHERE watch_id = ? AND kind = 'status' ORDER BY id DESC LIMIT 1", (watch["id"],))
        if not last or db.from_json(last["payload"], {}).get("status") == "ok":
            return  # we never told them it was down, so don't tell them it's back
        headline, link = f"{name} is back to normal", app_link(f"/pages/{watch['id']}")
        material = f"status:{watch['id']}:ok:{datetime.now(timezone.utc).isoformat(timespec='minutes')}"
    elif status == "region_missing":
        headline, link = f"{name}: the region you picked is missing", app_link(f"/pages/{watch['id']}/picker")
        material = f"status:{watch['id']}:region:{today}"
    else:
        headline, link = f"We can't reach {name}", app_link(f"/pages/{watch['id']}")
        material = f"status:{watch['id']}:{status}:{today}"
    msg = AlertMessage(kind="status", page_name=name, page_url=target["url"], headline=headline,
                       summary=f"Status alert, not a content change. {message}", link=link, when=local_time(user))
    # The stored status lets a later recovery know a "can't reach" alert was actually sent.
    await dispatch(user, watch, "status", material, msg, extra_payload={"status": status})


async def on_flapping(watch: dict) -> None:
    """At most one "this page is changing a lot" message per watch per day."""
    ctx = await _context(watch)
    if not ctx:
        return
    user, target = ctx
    name = watch["name"] or display_domain(target["url"])
    msg = AlertMessage(kind="flapping", page_name=name, page_url=target["url"], headline=f"{name} is changing a lot",
                       summary="We've raised its sensitivity until tomorrow so you only hear about bigger changes.",
                       link=app_link(f"/pages/{watch['id']}"), when=local_time(user))
    await dispatch(user, watch, "flapping", f"flapping:{watch['id']}:{datetime.now(timezone.utc).date().isoformat()}", msg)


async def on_threshold(watch: dict, kind: str, value: float, raw: str) -> None:
    """A tracked number crossed a threshold (the checker only calls this on the crossing itself)."""
    ctx = await _context(watch)
    if not ctx:
        return
    user, target = ctx
    name = watch["name"] or display_domain(target["url"])
    th = db.from_json(watch.get("number_thresholds"), {})
    words = {"below": f"dropped below {th.get('below')}", "above": f"rose above {th.get('above')}",
             "change_pct": f"moved by more than {th.get('change_pct')}%"}[kind]
    msg = AlertMessage(kind="threshold", page_name=name, page_url=target["url"], headline=f"{name}: tracked number {words}",
                       summary=f"It's now {raw}.", link=app_link(f"/pages/{watch['id']}?tab=numbers"), when=local_time(user))
    await dispatch(user, watch, "threshold", f"threshold:{watch['id']}:{kind}:{db.now_iso()}", msg)


async def send_test(user: dict, channel: str) -> tuple[bool, str]:
    """Settings → "Send test". Sends immediately (no dedupe) and reports the result in plain words."""
    reason = channel_ready(channel, user)
    if reason:
        return False, reason
    msg = AlertMessage(kind="test", page_name="Test alert", page_url=settings.base_url, headline="ChangeWatch test alert",
                       summary=f"If you can read this, {channel} alerts work.", link=app_link("/settings"), when=local_time(user))
    try:
        await send_via(channel, user, msg)
    except NotConfigured as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"Sending failed: {exc}"[:300]
    return True, {"email": f"Test email sent to {user['email']}.", "telegram": "Test message sent to Telegram.",
                  "discord": "Test message sent to Discord."}[channel]
