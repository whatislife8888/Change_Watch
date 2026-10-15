"""
routes/picker.py — the visual picker's API: open a session, serve the sanitised frame, test a selection,
and save selectors (which re-baselines the watch).
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .. import checker, db, extract, numbers
from ..auth import current_user
from ..config import settings
from ..errors import ApiError
from ..jobqueue import queue
from ..picker.frame import build_csp, message_page, sanitise
from ..schemas import PickerSession, PickerTestOut, SelectorsIn, WatchDetail
from ..views import get_watch_row, watch_detail

router = APIRouter(prefix="/api/watches", tags=["picker"])

# Why a signed token in the URL instead of the cookie: the frame is a sandboxed iframe with an opaque
# origin, and browsers may not send cookies to it. A 10-minute signed token works everywhere.
_signer = URLSafeTimedSerializer(settings.secret_key, salt="cw-picker")
TOKEN_MAX_AGE = 600


async def latest_html(target_id: int) -> str | None:
    fetch = await db.fetch_one(
        "SELECT * FROM fetches WHERE target_id = ? AND html_path IS NOT NULL ORDER BY id DESC LIMIT 1", (target_id,))
    return checker.read_fetch_html(fetch)


def valid_selector(selector: str) -> bool:
    try:
        extract.parse("<p></p>").select(selector)
        return True
    except Exception:
        return False


@router.post("/{watch_id}/picker/session", response_model=PickerSession)
async def picker_session(watch_id: int, user: dict = Depends(current_user)) -> dict:
    row = await get_watch_row(watch_id, user["id"])
    if not row:
        raise ApiError(404, "watch_not_found", "That page isn't in your list.")
    token = _signer.dumps({"w": watch_id, "u": user["id"]})
    return {"frame_url": f"/api/watches/{watch_id}/picker/frame?token={token}"}


@router.get("/{watch_id}/picker/frame", response_class=HTMLResponse, include_in_schema=False)
async def picker_frame(watch_id: int, token: str = Query(...)) -> HTMLResponse:
    try:
        data = _signer.loads(token, max_age=TOKEN_MAX_AGE)
    except SignatureExpired:
        body, nonce = message_page("This picker session expired. Reload the page to start a new one.")
        return HTMLResponse(body, headers={"Content-Security-Policy": build_csp(nonce)})
    except BadSignature:
        raise ApiError(403, "bad_token", "Invalid picker link.") from None
    if data.get("w") != watch_id:
        raise ApiError(403, "bad_token", "Invalid picker link.")
    row = await get_watch_row(watch_id, data["u"])
    if not row:
        raise ApiError(404, "watch_not_found", "That page isn't in your list.")
    html = await latest_html(row["target_id"])
    if not html:
        body, nonce = message_page("The first check hasn't finished yet. Try again in a few seconds.")
    else:
        body, nonce = sanitise(html, row["url"])
    return HTMLResponse(body, headers={
        "Content-Security-Policy": build_csp(nonce),
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
    })


@router.post("/{watch_id}/picker/test", response_model=PickerTestOut)
async def picker_test(watch_id: int, body: SelectorsIn, user: dict = Depends(current_user)) -> dict:
    """Preview what text a selection would watch (and which number it would track) on the stored page."""
    row = await get_watch_row(watch_id, user["id"])
    if not row:
        raise ApiError(404, "watch_not_found", "That page isn't in your list.")
    html = await latest_html(row["target_id"])
    if not html:
        return {"text_preview": "", "number_preview": None, "missing_selectors": [], "available": False}
    ex = extract.extract(html, body.watch_selectors, body.ignore_selectors, bool(row["ignore_carousels"]))
    number = numbers.extract_number(html, body.number_selector, row["number_regex"]) if body.number_selector else None
    return {
        "text_preview": ex.text[:3000],
        "number_preview": number[1] if number else None,
        "missing_selectors": ex.missing_selectors + [s for s in ex.invalid_selectors if s not in ex.missing_selectors],
        "available": True,
    }


@router.put("/{watch_id}/selectors", response_model=WatchDetail)
async def save_selectors(watch_id: int, body: SelectorsIn, user: dict = Depends(current_user)) -> dict:
    """Save picked regions and re-baseline: the next comparison starts from the new selection (no alert)."""
    row = await get_watch_row(watch_id, user["id"])
    if not row:
        raise ApiError(404, "watch_not_found", "That page isn't in your list.")
    def clean(items: list[str]) -> list[str]:
        return [s.strip() for s in items if s and s.strip()][:20]

    watch_sel, ignore_sel = clean(body.watch_selectors), clean(body.ignore_selectors)
    number_sel = (body.number_selector or "").strip() or None
    for sel in watch_sel + ignore_sel + ([number_sel] if number_sel else []):
        if not valid_selector(sel):
            raise ApiError(422, "invalid_selector", f"“{sel}” isn't a valid CSS selector.")
    await db.execute(
        "UPDATE watches SET watch_selectors = ?, ignore_selectors = ?, number_selector = ? WHERE id = ?",
        (db.to_json(watch_sel), db.to_json(ignore_sel), number_sel, watch_id))
    await checker.rebaseline(watch_id)
    # Check soon so the crop and element boxes for the new regions are captured.
    await db.execute("UPDATE watches SET next_due_at = NULL WHERE id = ?", (watch_id,))
    queue.enqueue(row["target_id"], priority=0, reason="regions changed")
    fresh = await get_watch_row(watch_id, user["id"])
    assert fresh is not None
    return await watch_detail(fresh)
