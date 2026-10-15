"""
config.py — all settings, read from environment variables (or backend/.env).

Who uses it: almost every backend module imports `settings` from here.
Depends on: pydantic-settings, which reads env vars and converts them to the right Python types.

Why a settings object instead of os.environ everywhere: one place documents every knob, gives each a
safe default, and validates types (e.g. WORKER_COUNT must be an int) at startup instead of mid-check.
"""
from pathlib import Path
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every configurable value. Names match env vars case-insensitively (BASE_URL -> base_url)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    base_url: str = "http://localhost:5173"
    secret_key: str = "dev-insecure-secret-change-me"
    data_dir: Path = Path("./data")
    frontend_dist: str = ""
    cors_origins: str = ""
    worker_count: int = 3
    max_browser_pages: int = 3
    domain_min_gap_seconds: float = 10.0
    confirm_refetch: bool = True
    allow_demo_page: bool = True
    admin_email: str = ""
    debug_fast_schedule: bool = False

    email_provider: str = "smtp"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    resend_api_key: str = ""

    telegram_bot_token: str = ""

    anthropic_api_key: str = ""
    ai_model: str = "claude-haiku-5-5"

    # ----- derived helpers (not env vars) -----

    @property
    def base_origin(self) -> str:
        """The scheme://host[:port] part of BASE_URL, used for Origin (CSRF) checks."""
        parts = urlsplit(self.base_url)
        return f"{parts.scheme}://{parts.netloc}"

    @property
    def is_https(self) -> bool:
        """True in production (HTTPS), which turns on the Secure flag for cookies."""
        return self.base_url.startswith("https://")

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS_ORIGINS split into a list (only used for optional split hosting)."""
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def email_configured(self) -> bool:
        """Whether any email provider has the credentials it needs."""
        if self.email_provider == "resend":
            return bool(self.resend_api_key)
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    @property
    def ai_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    def minutes_to_seconds(self, minutes: float) -> float:
        """Convert a check interval to seconds.

        Why: DEBUG_FAST_SCHEDULE lets us test scheduling locally by treating "minutes" as seconds,
        so a 15-minute watch is checked every 15 seconds. Never enable it in production.
        """
        return minutes if self.debug_fast_schedule else minutes * 60


settings = Settings()


def data_path(*parts: str) -> Path:
    """Build a path inside DATA_DIR and make sure its parent folder exists."""
    path = settings.data_dir.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
