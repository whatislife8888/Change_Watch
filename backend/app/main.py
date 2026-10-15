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
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

import truststore
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from . import checker, db, media, rss
from .config import settings
from .errors import ApiError, install_error_handlers
from .fetcher import fetcher
from .jobqueue import queue
from .politeness import politeness
from .routes import auth as auth_routes
from .routes import events as event_routes
from .routes import picker as picker_routes
from .routes import settings as settings_routes
from .routes import templates as template_routes
from .routes import public as public_routes
from .routes import stats as stats_routes
from .routes import watches as watch_routes
from .scheduler import Scheduler, reset_stuck_targets
from .security import OriginCheckMiddleware

# Use the operating system's certificate store for HTTPS (robots.txt, Telegram, Discord, AI...).
# Why: on networks that inspect TLS, Python's bundled certificates reject valid connections.
# Done before any HTTPS client is created (they're all created per request, after startup).
truststore.inject_into_ssl()

# The web app manifest needs its own content type for browsers to treat the site as installable.
mimetypes.add_type("application/manifest+json", ".webmanifest")

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
    await politeness.restore_from_db()
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
               picker_routes.router, settings_routes.router, template_routes.router, public_routes.router,
               media.router, rss.router):
    app.include_router(router)

FRONTEND = Path(settings.frontend_dist) if settings.frontend_dist else None


@app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def spa(full_path: str) -> Response:
    """Serve the built frontend: a real file if it exists, otherwise index.html (SPA fallback)."""
    if full_path.startswith(("api/", "rss/")):
        raise ApiError(404, "not_found", "Not found.")
    if not FRONTEND or not FRONTEND.exists():
        raise ApiError(404, "not_found", "Frontend not built. In development open http://localhost:5173.")
    candidate = (FRONTEND / full_path).resolve()
    if full_path and candidate.is_file() and FRONTEND.resolve() in candidate.parents:
        # Vite puts a content hash in asset file names, so they can be cached forever. The service worker and
        # manifest must always be re-checked, or phones would keep running an old version of the app.
        if full_path.startswith("assets/"):
            cache = "public, max-age=31536000, immutable"
        elif full_path in ("sw.js", "manifest.webmanifest", "asset-manifest.json"):
            cache = "no-cache"
        else:
            cache = "public, max-age=3600"
        return FileResponse(candidate, headers={"Cache-Control": cache})
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})
