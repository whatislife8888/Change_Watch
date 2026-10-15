"""
routes/events.py — GET /api/events: the live Server-Sent Events stream for the logged-in user.

SSE in one sentence: the browser opens one long HTTP response and the server keeps writing small
"event: name / data: json" blocks into it whenever something happens. Simpler than WebSockets because
data only flows server → browser, and the browser's EventSource reconnects automatically.
"""
import asyncio
import json

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from ..auth import current_user
from ..events import bus
from ..jobqueue import queue

router = APIRouter(tags=["events"])
PING_S = 15


@router.get("/api/events")
async def events(request: Request, user: dict = Depends(current_user)) -> EventSourceResponse:
    q = bus.subscribe(user["id"])

    async def stream():
        try:
            yield {"event": "queue", "data": json.dumps(queue.stats())}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=PING_S)
                    yield {"event": item["event"], "data": json.dumps(item["data"])}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            bus.unsubscribe(user["id"], q)

    # X-Accel-Buffering: no tells proxies (nginx, Railway's edge) not to hold events back in a buffer.
    return EventSourceResponse(stream(), headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}, ping=3600)
