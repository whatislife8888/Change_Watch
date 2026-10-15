"""
scheduler.py — the clock that decides *when* targets are checked (requirement 2).

Who uses it: main.py starts it; it hands work to jobqueue.py.
Depends on: db, jobqueue, events (queue heartbeat), digest + cleanup tasks.

Every 20 seconds `tick()` asks the database: which targets have next_fetch_at in the past, aren't
running, and still have at least one un-paused watch? Each is enqueued at priority 1. The checker sets
the next next_fetch_at with ±10% random jitter, so targets added at the same moment drift apart
instead of all firing together.

The same module runs the small maintenance loops: the queue heartbeat for the live UI (every 3 s),
the daily digest (every 10 minutes) and file cleanup (every 6 hours).
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from . import db
from .config import settings
from .events import bus
from .jobqueue import JobQueue

log = logging.getLogger("changewatch.scheduler")

TICK_S = 20


def jittered(seconds: float) -> float:
    """seconds ± 10%. Why: if 50 targets are due at 09:00, jitter spreads them over a few minutes."""
    return seconds * (0.9 + random.random() * 0.2)


def iso_in(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).replace(microsecond=0).isoformat()


class Scheduler:
    def __init__(self, queue: JobQueue) -> None:
        self.queue = queue
        self._tasks: list[asyncio.Task] = []

    def start(self) -> None:
        from . import digest, maintenance  # imported here to avoid import cycles at module load

        self._tasks = [
            asyncio.create_task(self._loop(), name="scheduler"),
            asyncio.create_task(self._heartbeat(), name="queue-heartbeat"),
            asyncio.create_task(digest.digest_loop(), name="digest"),
            asyncio.create_task(maintenance.cleanup_loop(), name="cleanup"),
        ]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _loop(self) -> None:
        tick = 2 if settings.debug_fast_schedule else TICK_S
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("Scheduler tick failed")
            await asyncio.sleep(tick)

    async def tick(self) -> int:
        """Enqueue every due target. Returns how many were enqueued."""
        now = db.now_iso()
        rows = await db.fetch_all(
            """
            SELECT t.id FROM targets t
            WHERE (t.next_fetch_at IS NULL OR t.next_fetch_at <= ?)
              AND t.running_since IS NULL
              AND EXISTS (SELECT 1 FROM watches w WHERE w.target_id = t.id AND w.paused = 0)
            ORDER BY t.next_fetch_at
            LIMIT 200
            """,
            (now,),
        )
        count = 0
        for row in rows:
            if not self.queue.is_busy(row["id"]):
                self.queue.enqueue(row["id"], priority=1, reason="scheduled")
                count += 1
        return count

    async def _heartbeat(self) -> None:
        """Every 3 s, tell connected browsers how busy the queue is (drives the Movement animation)."""
        while True:
            await asyncio.sleep(3)
            if bus.connected:
                bus.broadcast("queue", self.queue.stats())


async def reset_stuck_targets() -> int:
    """On startup, clear `running_since` left over from a crash or restart.

    Why all of them: the queue lives in this process, so after a restart nothing can genuinely be running.
    Any target older than 5 minutes is certainly stale; younger ones are too, for the same reason.
    """
    return await db.execute_rowcount("UPDATE targets SET running_since = NULL WHERE running_since IS NOT NULL")
