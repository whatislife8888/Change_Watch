"""
Tests for alert dedupe: the same change can never be alerted twice on the same channel,
even if the checker runs again (retry, restart, race).
"""
import asyncio

import pytest

from app import alerts, db


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(db.settings, "data_dir", tmp_path)
    asyncio.run(db.connect())
    yield
    asyncio.run(db.close())


async def _setup() -> tuple[dict, dict, dict]:
    uid = await db.execute("INSERT INTO users (email, password_hash, created_at) VALUES ('a@b.c', 'x', ?)", (db.now_iso(),))
    tid = await db.execute("INSERT INTO targets (url, domain, dial_seed, created_at) VALUES ('https://e.com/', 'e.com', 'abcd1234', ?)", (db.now_iso(),))
    wid = await db.execute(
        "INSERT INTO watches (user_id, target_id, name, interval_minutes, rss_token, created_at, alert_email, alert_discord) "
        "VALUES (?, ?, 'E', 60, 'tok', ?, 1, 1)", (uid, tid, db.now_iso()))
    sid = await db.execute(
        "INSERT INTO snapshots (watch_id, content_hash, text, raw_text, created_at, change_summary) VALUES (?, 'h1', 't', 't', ?, 's')",
        (wid, db.now_iso()))
    user = await db.fetch_one("SELECT * FROM users WHERE id = ?", (uid,))
    watch = await db.fetch_one("SELECT * FROM watches WHERE id = ?", (wid,))
    snap = await db.fetch_one("SELECT * FROM snapshots WHERE id = ?", (sid,))
    return user, watch, snap


def test_same_change_alerted_once_per_channel(database):
    async def run():
        user, watch, snap = await _setup()
        await alerts.on_change(watch, snap, None, [("+", "x")])
        await alerts.on_change(watch, snap, None, [("+", "x")])  # e.g. a retried job
        rows = await db.fetch_all("SELECT channel, status FROM alerts")
        return rows
    rows = asyncio.run(run())
    assert sorted(r["channel"] for r in rows) == ["discord", "email"]
    # Not configured in tests: recorded as failed with a reason, never crashing.
    assert all(r["status"] == "failed" for r in rows)


def test_new_content_hash_is_a_new_alert(database):
    async def run():
        user, watch, snap = await _setup()
        await alerts.on_change(watch, snap, None, [])
        snap2 = {**snap, "id": snap["id"], "content_hash": "h2"}
        await alerts.on_change(watch, snap2, None, [])
        return await db.fetch_value("SELECT COUNT(*) FROM alerts")
    assert asyncio.run(run()) == 4


def test_claim_is_atomic(database):
    async def run():
        user, watch, snap = await _setup()
        results = await asyncio.gather(*[alerts.claim(user, watch["id"], None, "change", "email", "same-key") for _ in range(5)])
        return [r for r in results if r is not None]
    assert len(asyncio.run(run())) == 1


def test_discord_webhook_validation():
    assert alerts.valid_discord_webhook("https://discord.com/api/webhooks/1/abc")
    assert not alerts.valid_discord_webhook("http://169.254.169.254/api/webhooks/1")
    assert not alerts.valid_discord_webhook("https://evil.com/api/webhooks/1/abc")


def test_daily_digest_batches_into_one_message(database):
    from app import digest

    async def run():
        user, watch, snap = await _setup()
        await db.execute("UPDATE users SET digest_mode = 'daily', digest_hour = 0 WHERE id = ?", (user["id"],))
        user = await db.fetch_one("SELECT * FROM users WHERE id = ?", (user["id"],))
        # Three changes arrive during the day: all queued, nothing sent yet.
        for h in ("h1", "h2", "h3"):
            await alerts.on_change(watch, {**snap, "content_hash": h}, None, [("+", "x")])
        queued = await db.fetch_value("SELECT COUNT(*) FROM alerts WHERE status = 'queued_digest'")
        sent = await digest.send_digest(user, force=True)
        digest_rows = await db.fetch_all("SELECT channel FROM alerts WHERE dedupe_key IN (SELECT dedupe_key FROM alerts WHERE payload LIKE '%\"digest\": true%')")
        again = await digest.send_digest(await db.fetch_one("SELECT * FROM users WHERE id = ?", (user["id"],)), force=True)
        return queued, sent, len(digest_rows), again
    queued, sent, digest_messages, again = asyncio.run(run())
    assert queued == 3          # changes were held back
    assert sent == 3            # one digest covering all three
    assert digest_messages == 1 # one message (email only: no Telegram/Discord set up)
    assert again == 0           # nothing new -> nothing sent
