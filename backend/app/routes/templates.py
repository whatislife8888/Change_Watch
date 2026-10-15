"""
routes/templates.py — shared setups ("Share setup" → /import/{token}).

A template stores a page's URL, regions, ignore rules, keywords, sensitivity and interval — never the
owner's alert settings or contact details. Another user can preview it and add the same page in one click.
"""
from fastapi import APIRouter, Depends

from .. import db
from ..auth import current_user
from ..errors import ApiError
from ..schemas import TemplateOut, WatchCreate, WatchDetail
from ..urlnorm import dial_seed, display_domain
from .watches import create_watch_for

router = APIRouter(prefix="/api/templates", tags=["templates"])


async def load_template(token: str) -> dict:
    row = await db.fetch_one(
        "SELECT t.*, u.display_name, u.email FROM templates t JOIN users u ON u.id = t.owner_user_id WHERE t.token = ?", (token,))
    if not row:
        raise ApiError(404, "template_not_found", "This shared setup doesn't exist.")
    return row


@router.get("/{token}", response_model=TemplateOut)
async def get_template(token: str, _: dict = Depends(current_user)) -> dict:
    row = await load_template(token)
    config = db.from_json(row["config"], {})
    return {
        "token": token, "config": config,
        "owner_name": row["display_name"] or row["email"].split("@")[0],
        "domain": display_domain(config["url"]), "dial_seed": dial_seed(config["url"]),
        "created_at": row["created_at"],
    }


@router.post("/{token}/import", response_model=WatchDetail, status_code=201)
async def import_template(token: str, user: dict = Depends(current_user)) -> dict:
    row = await load_template(token)
    c = db.from_json(row["config"], {})
    body = WatchCreate(url=c["url"], name=c.get("name", ""), interval_minutes=c.get("interval_minutes", 60),
                       sensitivity=c.get("sensitivity", "medium"), keywords=c.get("keywords", []),
                       keyword_mode=c.get("keyword_mode", "off"))
    return await create_watch_for(user, body, extra={
        "watch_selectors": c.get("watch_selectors", []), "ignore_selectors": c.get("ignore_selectors", []),
        "ignore_carousels": c.get("ignore_carousels", True), "number_selector": c.get("number_selector"),
        "number_regex": c.get("number_regex"),
    })
