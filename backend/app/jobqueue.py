"""
jobqueue.py — the job queue and its workers (requirement 2).

Who uses it: scheduler.py (enqueues due targets), routes/watches.py ("Check now", new watches),
routes/stats.py + events (queue size for the Movement animation).
Depends on: asyncio only. The actual work is a handler function passed in (checker.check_target).

How it works:
- An asyncio.PriorityQueue holds jobs. Priority 0 = a user is waiting (first check, Check now);
  priority 1 = scheduled. Lower numbers come out first.
- WORKER_COUNT worker coroutines loop forever: take a job, run it, repeat.
- In-flight dedupe: `queued` and `running` remember which targets are waiting or being checked, so the
  same target is never queued twice. A "Check now" on a target that's already waiting just attaches to
  that job (and bumps it to priority 0).
- Retries: up to 3 attempts per job, with backoff of 5 s, 20 s, 60 s plus random jitter, and only for
  failures that might succeed next time (timeouts, network errors, 5xx, browser crashes).

Swapping in Redis later would mean reimplementing this class's enqueue/worker loop; nothing else changes.
"""
import asyncio
import itertools
import logging
import random
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from .config import settings

log = logging.getLogger("changewatch.jobqueue")

MAX_ATTEMPTS = 3
BACKOFF_S = [5, 20, 60]
# Safety net for a whole job (render + possible confirmation render + saving). Each render has its own
# 45 s timeout inside fetcher.py; this only catches something truly stuck.
JOB_TIMEOUT_S = 240
LONG_RETRY_AFTER_S = 120


@dataclass
class AttemptResult:
    """What one attempt reports back to the queue."""
    retryable: bool = False
    retry_after: float | None = None


@dataclass(order=True)
class Job:
    priority: int
    seq: int
    target_id: int = field(compare=False)
    reason: str = field(compare=False)


Handler = Callable[[int, int, bool, int], Awaitable[AttemptResult]]


class JobQueue:
    def __init__(self, worker_count: int) -> None:
        self.worker_count = worker_count
        self._queue: asyncio.PriorityQueue[Job] = asyncio.PriorityQueue()
        self._seq = itertools.count()
        self.queued: dict[int, int] = {}  # target_id -> priority of the live queue entry
        self.running: dict[int, int] = {}  # target_id -> worker index
        self.workers_busy: list[int | None] = [None] * worker_count
        self._tasks: list[asyncio.Task] = []
        self._handler: Handler | None = None
        self._on_give_up: Callable[[int, int, str], Awaitable[None]] | None = None
        self.completed = 0

    def set_handler(self, handler: Handler, on_give_up: Callable[[int, int, str], Awaitable[None]]) -> None:
        self._handler = handler
        self._on_give_up = on_give_up

    def start(self) -> None:
        for i in range(self.worker_count):
            self._tasks.append(asyncio.create_task(self._worker(i), name=f"worker-{i}"))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    def is_busy(self, target_id: int) -> bool:
        return target_id in self.queued or target_id in self.running

    def enqueue(self, target_id: int, priority: int = 1, reason: str = "scheduled") -> str:
        """Add a target to the queue. Returns 'queued', 'attached' (already waiting) or 'running'."""
        if target_id in self.running:
            return "running"
        if target_id in self.queued:
            if priority < self.queued[target_id]:
                # Bump: push a higher-priority copy; the old entry is skipped when it comes out.
                self.queued[target_id] = priority
                self._queue.put_nowait(Job(priority, next(self._seq), target_id, reason))
            return "attached"
        self.queued[target_id] = priority
        self._queue.put_nowait(Job(priority, next(self._seq), target_id, reason))
        return "queued"

    def stats(self) -> dict:
        return {
            "running": len(self.running),
            "waiting": len(self.queued),
            "workers": self.worker_count,
            "workers_busy": [t is not None for t in self.workers_busy],
            "completed": self.completed,
        }

    async def _worker(self, index: int) -> None:
        while True:
            job = await self._queue.get()
            # Skip stale duplicates (an older entry for a target that was bumped or already handled).
            if self.queued.get(job.target_id) != job.priority:
                continue
            del self.queued[job.target_id]
            self.running[job.target_id] = index
            self.workers_busy[index] = job.target_id
            try:
                await self._run_with_retries(job)
            except asyncio.CancelledError:
                raise
            except Exception:  # never let one bad job kill a worker
                log.exception("Job for target %s crashed", job.target_id)
            finally:
                self.running.pop(job.target_id, None)
                self.workers_busy[index] = None
                self.completed += 1

    async def _run_with_retries(self, job: Job) -> None:
        assert self._handler is not None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            is_last = attempt == MAX_ATTEMPTS
            try:
                result = await asyncio.wait_for(self._handler(job.target_id, attempt, is_last, job.priority), JOB_TIMEOUT_S)
            except asyncio.TimeoutError:
                log.warning("Job for target %s timed out (attempt %s)", job.target_id, attempt)
                if self._on_give_up:
                    await self._on_give_up(job.target_id, attempt, "the whole check took too long")
                return
            except Exception:
                log.exception("Attempt %s for target %s raised", attempt, job.target_id)
                result = AttemptResult(retryable=True)
            if not result.retryable or is_last:
                return
            if result.retry_after and result.retry_after > LONG_RETRY_AFTER_S:
                return  # the handler already scheduled the next check after Retry-After
            delay = result.retry_after or BACKOFF_S[attempt - 1]
            # Jitter: +0..30% so many failing jobs don't all retry at the same instant.
            await asyncio.sleep(delay * (1 + random.random() * 0.3))


# The one queue for the whole app (main.py connects it to checker.check_target at startup).
queue = JobQueue(settings.worker_count)
