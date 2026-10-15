"""
routes/settings.py — the user's profile, alert channels, digest preferences, and "Send test".
"""
from zoneinfo import ZoneInfo, available_timezones

import httpx
from fastapi import APIRouter, Depends

from .. import alerts, db
from ..auth import current_user
from ..config import settings
from ..errors import ApiError
from ..schemas import SettingsIn, SettingsOut, TestAlertIn, TestAlertOut

router = APIRouter(prefix="/api/settings", tags=["settings"])
_bot_username: dict[str, str | None] = {}


async def bot_username(token: str) -> str | None:
    """@username of the Telegram bot (so Settings can say "message @ChangeWatchBot"). Cached."""
    if token in _bot_username:
        return _bot_username[token]
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"https://api.telegram.org/bot{token}/getMe")
        name = r.json().get("result", {}).get("username") if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        name = None
    _bot_username[token] = name
    return name


async def settings_out(user: dict) -> dict:
    token = user.get("telegram_bot_token") or settings.telegram_bot_token
    return {
        "email": user["email"],
        "display_name": user["display_name"],
        "timezone": user["timezone"],
        "digest_mode": user["digest_mode"],
        "digest_hour": user["digest_hour"],
        "telegram_chat_id": user["telegram_chat_id"],
        "telegram_has_own_bot": bool(user.get("telegram_bot_token")),
        "discord_webhook_url": user["discord_webhook_url"],
        "email_available": settings.email_configured,
        "telegram_available": bool(token),
        "ai_available": settings.ai_configured,
        "telegram_bot_username": await bot_username(token) if token else None,
    }


@router.get("", response_model=SettingsOut)
async def get_settings(user: dict = Depends(current_user)) -> dict:
    return await settings_out(user)


@router.put("", response_model=SettingsOut)
async def put_settings(body: SettingsIn, user: dict = Depends(current_user)) -> dict:
    data = body.model_dump(exclude_unset=True)
    updates: dict = {}
    if "display_name" in data and data["display_name"] is not None:
        updates["display_name"] = data["display_name"].strip()
    if data.get("timezone"):
        if data["timezone"] not in available_timezones():
            raise ApiError(422, "invalid_timezone", "Choose a timezone from the list.")
        ZoneInfo(data["timezone"])
        updates["timezone"] = data["timezone"]
    if data.get("digest_mode"):
        updates["digest_mode"] = data["digest_mode"]
    if data.get("digest_hour") is not None:
        updates["digest_hour"] = data["digest_hour"]
    if "telegram_chat_id" in data:
        chat = (data["telegram_chat_id"] or "").strip()
        if chat and not chat.lstrip("-").isdigit() and not chat.startswith("@"):
            raise ApiError(422, "invalid_chat_id", "A Telegram chat id is a number like 123456789 (or @channelname).")
        updates["telegram_chat_id"] = chat or None
    if "telegram_bot_token" in data:
        updates["telegram_bot_token"] = (data["telegram_bot_token"] or "").strip() or None
    if "discord_webhook_url" in data:
        url = (data["discord_webhook_url"] or "").strip()
        if url and not alerts.valid_discord_webhook(url):
            raise ApiError(422, "invalid_webhook", "Paste a Discord webhook URL (https://discord.com/api/webhooks/...).")
        updates["discord_webhook_url"] = url or None
    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        await db.execute(f"UPDATE users SET {sets} WHERE id = ?", (*updates.values(), user["id"]))
    fresh = await db.fetch_one("SELECT * FROM users WHERE id = ?", (user["id"],))
    assert fresh is not None
    return await settings_out(fresh)


@router.post("/test-alert", response_model=TestAlertOut)
async def test_alert(body: TestAlertIn, user: dict = Depends(current_user)) -> dict:
    ok, message = await alerts.send_test(user, body.channel)
    return {"ok": ok, "message": message}
