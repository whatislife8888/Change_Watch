"""
main.py — creates the FastAPI app and wires everything together.

Who uses it: Uvicorn (`uvicorn app.main:app`).
Depends on: db, errors, security (Origin middleware), and every router in routes/.
"""
from contextlib import asynccontextmanager

import truststore

# Use the operating system's certificate store for HTTPS (robots.txt, Telegram, Discord, AI...).
# Why: on networks that inspect TLS, Python's bundled certificates reject valid connections.
truststore.inject_into_ssl()

from fastapi import FastAPI  # noqa: E402

from . import db  # noqa: E402
from .errors import install_error_handlers  # noqa: E402
from .routes import auth as auth_routes  # noqa: E402
from .security import OriginCheckMiddleware  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup (before `yield`) and once at shutdown (after `yield`)."""
    await db.connect()
    yield
    await db.close()


app = FastAPI(title="ChangeWatch API", lifespan=lifespan, openapi_url="/api/openapi.json", docs_url="/api/docs")
install_error_handlers(app)
app.add_middleware(OriginCheckMiddleware)
app.include_router(auth_routes.router)


@app.get("/api/health")
async def api_health() -> dict:
    """Tiny endpoint the frontend calls to prove the dev proxy works."""
    return {"ok": True}
