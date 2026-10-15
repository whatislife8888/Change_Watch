"""
main.py — creates the FastAPI app and wires everything together.

Who uses it: Uvicorn (`uvicorn app.main:app`).
Depends on: db (connect on startup).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup (before `yield`) and once at shutdown (after `yield`)."""
    await db.connect()
    yield
    await db.close()


app = FastAPI(title="ChangeWatch API", lifespan=lifespan, openapi_url="/api/openapi.json", docs_url="/api/docs")


@app.get("/api/health")
async def api_health() -> dict:
    """Tiny endpoint the frontend calls to prove the dev proxy works."""
    return {"ok": True}
