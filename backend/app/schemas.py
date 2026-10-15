"""
schemas.py — the API contract: every request body and response shape, as Pydantic models.

Who uses it: the route handlers (to validate input and shape output) and, indirectly, the frontend —
FastAPI turns these models into an OpenAPI document at /api/openapi.json, and `npm run gen:api`
generates TypeScript types from it. One source of truth, so the two apps can't drift apart.
"""
from typing import Literal

from pydantic import BaseModel, Field

Sensitivity = Literal["low", "medium", "high"]
KeywordMode = Literal["off", "appear", "disappear", "any"]

MIN_INTERVAL = 15
MAX_INTERVAL = 1440


# ---------- auth / users ----------

class SignupIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(default="", max_length=80)


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    timezone: str
    is_admin: bool


# ---------- url preview ----------

class UrlPreviewIn(BaseModel):
    url: str = Field(max_length=2048)


class UrlPreviewOut(BaseModel):
    valid: bool
    normalised_url: str | None = None
    domain: str | None = None
    dial_seed: str | None = None
    error: str | None = None
    already_watching_id: int | None = None
    other_watchers: int = 0


# ---------- watches ----------

class NumberThresholds(BaseModel):
    below: float | None = None
    above: float | None = None
    change_pct: float | None = None


class WatchCreate(BaseModel):
    url: str = Field(max_length=2048)
    name: str = Field(default="", max_length=120)
    interval_minutes: int = 60
    sensitivity: Sensitivity = "medium"
    keywords: list[str] = Field(default_factory=list)
    keyword_mode: KeywordMode = "off"
    alert_email: bool = True
    alert_telegram: bool = False
    alert_discord: bool = False


class WatchPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    interval_minutes: int | None = None
    sensitivity: Sensitivity | None = None
    keywords: list[str] | None = None
    keyword_mode: KeywordMode | None = None
    number_selector: str | None = None
    number_regex: str | None = None
    number_thresholds: NumberThresholds | None = None
    alert_email: bool | None = None
    alert_telegram: bool | None = None
    alert_discord: bool | None = None
    paused: bool | None = None
    ignore_carousels: bool | None = None


class VolatileRule(BaseModel):
    kind: Literal["text", "selector"]
    value: str
    sample: str = ""
    learned_at: str
    hits: int = 0


class OutcomeItem(BaseModel):
    outcome: str
    at: str


class WatchSummary(BaseModel):
    id: int
    name: str
    url: str
    domain: str
    dial_seed: str
    status: str
    status_message: str | None
    paused: bool
    interval_minutes: int
    last_checked_at: str | None
    last_changed_at: str | None
    next_due_at: str | None
    versions: int
    shared_watchers: int
    is_running: bool
    is_queued: bool
    number_latest: float | None
    number_spark: list[float]
    flapping_until: str | None


class WatchDetail(WatchSummary):
    watch_selectors: list[str]
    ignore_selectors: list[str]
    ignore_carousels: bool
    sensitivity: Sensitivity
    keywords: list[str]
    keyword_mode: KeywordMode
    number_selector: str | None
    number_regex: str | None
    number_thresholds: NumberThresholds
    alert_email: bool
    alert_telegram: bool
    alert_discord: bool
    rss_url: str
    volatile_rules: list[VolatileRule]
    recent_outcomes: list[OutcomeItem]
    builtin_noise_selectors: dict[str, list[str]]
    created_at: str
    last_error: str | None


class CheckQueued(BaseModel):
    queued: bool
    attached: bool = False


# ---------- snapshots / compare ----------

class SnapshotItem(BaseModel):
    id: int
    created_at: str
    summary: str | None
    ai_summary: str | None
    added_lines: int
    removed_lines: int
    change_score: float
    thumbnail_url: str | None
    keyword_hit: str | None
    is_baseline: bool
    is_first: bool


class SnapshotDetail(SnapshotItem):
    watch_id: int
    raw_text: str
    screenshot_url: str | None
    crop_url: str | None


class CompareSide(BaseModel):
    id: int
    created_at: str
    summary: str | None


class DiffStats(BaseModel):
    added: int
    removed: int
    changed: int
    change_score: float


class DiffOp(BaseModel):
    """One block of the diff. `lines` is used by equal/insert/delete; `pairs` by replace.

    Each pair is {"old": [[tag, text], ...], "new": [[tag, text], ...]} where tag is
    equal | insert | delete — the word-level highlights inside a changed line.
    """
    type: Literal["equal", "insert", "delete", "replace"]
    lines: list[str] | None = None
    pairs: list[dict[str, list[list[str]]]] | None = None


class TextDiff(BaseModel):
    ops: list[DiffOp]
    stats: DiffStats


class Region(BaseModel):
    x: int
    y: int
    w: int
    h: int


class VisualDiff(BaseModel):
    before_url: str | None
    after_url: str | None
    width: int
    height_before: int
    height_after: int
    regions: list[Region]
    changed_percent: float
    shifted_by_px: int
    diff_image_url: str | None
    available: bool = True


class CompareResult(BaseModel):
    a: CompareSide
    b: CompareSide
    text: TextDiff
    visual: VisualDiff


class CheckLogItem(BaseModel):
    id: int
    started_at: str
    finished_at: str | None
    outcome: str
    attempt: int
    detail: str | None
    duration_ms: int | None
    watch_id: int | None


class NumberPoint(BaseModel):
    t: str
    value: float
    raw: str


class NumbersOut(BaseModel):
    points: list[NumberPoint]
    min: float | None
    max: float | None
    latest: float | None
    first: float | None
    change_pct: float | None
    changed_at: list[str]


# ---------- picker ----------

class PickerSession(BaseModel):
    frame_url: str


class SelectorsIn(BaseModel):
    watch_selectors: list[str] = Field(default_factory=list)
    ignore_selectors: list[str] = Field(default_factory=list)
    number_selector: str | None = None


class PickerTestOut(BaseModel):
    text_preview: str
    number_preview: str | None
    missing_selectors: list[str]
    available: bool = True


# ---------- settings / alerts ----------

class SettingsOut(BaseModel):
    email: str
    display_name: str
    timezone: str
    digest_mode: Literal["instant", "daily"]
    digest_hour: int
    telegram_chat_id: str | None
    telegram_has_own_bot: bool
    discord_webhook_url: str | None
    email_available: bool
    telegram_available: bool
    ai_available: bool
    telegram_bot_username: str | None = None


class SettingsIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    timezone: str | None = None
    digest_mode: Literal["instant", "daily"] | None = None
    digest_hour: int | None = Field(default=None, ge=0, le=23)
    telegram_chat_id: str | None = Field(default=None, max_length=64)
    telegram_bot_token: str | None = Field(default=None, max_length=128)
    discord_webhook_url: str | None = Field(default=None, max_length=512)


class TestAlertIn(BaseModel):
    channel: Literal["email", "telegram", "discord"]


class TestAlertOut(BaseModel):
    ok: bool
    message: str


# ---------- activity / stats ----------

class ActivityItem(BaseModel):
    kind: Literal["change", "first", "error", "blocked", "recovered", "baseline"]
    at: str
    watch_id: int
    watch_name: str
    domain: str
    dial_seed: str
    summary: str
    snapshot_id: int | None = None
    previous_snapshot_id: int | None = None
    added: int = 0
    removed: int = 0


class OverviewStats(BaseModel):
    total: int
    changed_today: int
    needs_attention: int
    paused: int
    running: int
    waiting: int


class DomainSlot(BaseModel):
    domain: str
    next_allowed_at: str | None
    busy: bool


class AdminStats(BaseModel):
    users: int
    watches: int
    targets: int
    sharing_ratio: float
    checks_24h: int
    outcome_counts: dict[str, int]
    ok_rate: float
    error_rate: float
    blocked_rate: float
    avg_render_ms: float | None
    renders_saved_24h: int
    queue: dict
    domains: list[DomainSlot]
    learned_rules: int
    top_shared: list[dict]


# ---------- templates / rss ----------

class TemplateConfig(BaseModel):
    url: str
    name: str
    watch_selectors: list[str]
    ignore_selectors: list[str]
    ignore_carousels: bool
    keywords: list[str]
    keyword_mode: KeywordMode
    sensitivity: Sensitivity
    interval_minutes: int
    number_selector: str | None = None
    number_regex: str | None = None


class TemplateOut(BaseModel):
    token: str
    config: TemplateConfig
    owner_name: str
    domain: str
    dial_seed: str
    created_at: str


class ShareOut(BaseModel):
    template_url: str
    token: str


class RssOut(BaseModel):
    rss_url: str
