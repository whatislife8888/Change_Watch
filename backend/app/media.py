"""
media.py — serves screenshots, crops, thumbnails and diff images, but only to users allowed to see them.

Who uses it: <img> tags on the Page detail and Compare screens.
Rule (from the spec): you may see an image only if you watch the page (target) it came from.
Files are immutable once written (named by id), so browsers may cache them privately for a day.
"""
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from . import db, visual_diff
from .auth import current_user
from .config import settings
from .errors import ApiError

router = APIRouter(prefix="/api/media", tags=["media"])
CACHE = {"Cache-Control": "private, max-age=86400, immutable"}


async def user_watches_target(user_id: int, target_id: int) -> bool:
    return bool(await db.fetch_one("SELECT 1 FROM watches WHERE user_id = ? AND target_id = ?", (user_id, target_id)))


def file_or_404(rel: str | None, media_type: str) -> FileResponse:
    if not rel:
        raise ApiError(404, "image_not_found", "That image isn't available.")
    path = Path(settings.data_dir, rel)
    if not path.exists():
        raise ApiError(404, "image_not_found", "That image isn't available any more.")
    return FileResponse(path, media_type=media_type, headers=CACHE)


async def snapshot_for_user(snapshot_id: int, user: dict) -> dict:
    row = await db.fetch_one(
        "SELECT s.*, w.target_id FROM snapshots s JOIN watches w ON w.id = s.watch_id WHERE s.id = ?", (snapshot_id,))
    if not row or not await user_watches_target(user["id"], row["target_id"]):
        raise ApiError(404, "image_not_found", "That image isn't available.")
    return row


@router.get("/fetch/{fetch_id}/screenshot.png")
async def fetch_screenshot(fetch_id: int, user: dict = Depends(current_user)) -> FileResponse:
    row = await db.fetch_one("SELECT target_id, screenshot_path FROM fetches WHERE id = ?", (fetch_id,))
    if not row or not await user_watches_target(user["id"], row["target_id"]):
        raise ApiError(404, "image_not_found", "That image isn't available.")
    return file_or_404(row["screenshot_path"], "image/png")


@router.get("/snapshot/{snapshot_id}/crop.png")
async def snapshot_crop(snapshot_id: int, user: dict = Depends(current_user)) -> FileResponse:
    row = await snapshot_for_user(snapshot_id, user)
    return file_or_404(row["crop_path"], "image/png")


@router.get("/snapshot/{snapshot_id}/thumb.jpg")
async def snapshot_thumb(snapshot_id: int, user: dict = Depends(current_user)) -> FileResponse:
    row = await snapshot_for_user(snapshot_id, user)
    return file_or_404(row["thumbnail_path"], "image/jpeg")


@router.get("/diff/{a}/{b}.png")
async def diff_image(a: int, b: int, user: dict = Depends(current_user)) -> FileResponse:
    await snapshot_for_user(a, user)
    await snapshot_for_user(b, user)
    path = visual_diff.diff_image_path(a, b)
    if not path.exists():
        raise ApiError(404, "image_not_found", "Open the comparison first to create this image.")
    return FileResponse(path, media_type="image/png", headers=CACHE)
