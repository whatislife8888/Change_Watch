"""
main.py — creates the FastAPI app and wires everything together.

Who uses it: Uvicorn (`uvicorn app.main:app`).
Depends on: every module. Startup order matters:
  1. database (migrations)  2. reset targets stuck "running" after a restart  3. Chromium
  4. job queue workers (connected to checker.check_target)  5. scheduler + maintenance loops
Shutdown runs the same steps in reverse.

In production FastAPI also serves the built React app (FRONTEND_DIST): real files are served as-is and
any other non-API GET returns index.html, so client-side routes like /pages/12 work on refresh.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import truststore

# Use the operating system's certificate store for HTTPS (robots.txt, Telegram, Discord, AI...).
# Why: on networks that inspect TLS, Python's bundled certificates reject valid connections.
truststore.inject_into_ssl()

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, Response  # noqa: E402

from . import checker, db, media  # noqa: E402
from .config import settings  # noqa: E402
from .errors import ApiError, install_error_handlers  # noqa: E402
from .fetcher import fetcher  # noqa: E402
from .jobqueue import queue  # noqa: E402
from .routes import auth as auth_routes  # noqa: E402
from .routes import events as event_routes  # noqa: E402
from .routes import picker as picker_routes  # noqa: E402
from .routes import public as public_routes  # noqa: E402
from .routes import stats as stats_routes  # noqa: E402
from .routes import watches as watch_routes  # noqa: E402
from .scheduler import Scheduler, reset_stuck_targets  # noqa: E402
from .security import OriginCheckMiddleware  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("changewatch")

scheduler = Scheduler(queue)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup (before `yield`) and once at shutdown (after `yield`)."""
    await db.connect()
    reset = await reset_stuck_targets()
    if reset:
        log.info("Reset %s target(s) left running by a previous process", reset)
    await fetcher.start()
    queue.set_handler(checker.check_target, checker.on_give_up)
    queue.start()
    scheduler.start()
    log.info("ChangeWatch ready (workers=%s, pages=%s, gap=%ss)", settings.worker_count, settings.max_browser_pages,
             settings.domain_min_gap_seconds)
    yield
    await scheduler.stop()
    await queue.stop()
    await fetcher.stop()
    await db.close()


app = FastAPI(title="ChangeWatch API", version="1.0", lifespan=lifespan,
              openapi_url="/api/openapi.json", docs_url="/api/docs", redoc_url=None)
install_error_handlers(app)
app.add_middleware(OriginCheckMiddleware)
if settings.cors_origin_list:
    # Only for optional split hosting (frontend on another domain). The default single container needs none.
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

for router in (auth_routes.router, watch_routes.router, stats_routes.router, event_routes.router,
               picker_routes.router, public_routes.router, media.router):
    app.include_router(router)


def _register_late_routers() -> None:
    """Routers added in later phases register here so the SPA fallback below always stays last."""
    import importlib

    for name in ("settings", "templates", "rss"):
        try:
            module = importlib.import_module(f"app.routes.{name}")
        except ModuleNotFoundError:
            continue
        app.include_router(module.router)


_register_late_routers()

FRONTEND = Path(settings.frontend_dist) if settings.frontend_dist else None


@app.get("/{full_path:path}", include_in_schema=False)
async def spa(full_path: str, request: Request) -> Response:
    """Serve the built frontend: a real file if it exists, otherwise index.html (SPA fallback)."""
    if full_path.startswith(("api/", "rss/")):
        raise ApiError(404, "not_found", "Not found.")
    if not FRONTEND or not FRONTEND.exists():
        raise ApiError(404, "not_found", "Frontend not built. In development open http://localhost:5173.")
    candidate = (FRONTEND / full_path).resolve()
    if full_path and candidate.is_file() and FRONTEND.resolve() in candidate.parents:
        # Vite puts a content hash in asset file names, so they can be cached forever.
        cache = "public, max-age=31536000, immutable" if full_path.startswith("assets/") else "public, max-age=3600"
        return FileResponse(candidate, headers={"Cache-Control": cache})
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})
