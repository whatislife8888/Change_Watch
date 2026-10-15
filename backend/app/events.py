"""
events.py — an in-process event bus that feeds Server-Sent Events (SSE) to browsers.

Who uses it: checker.py and jobqueue.py publish events; routes/events.py streams them to the browser.

How it works: every open browser tab that listens to /api/events gets its own asyncio.Queue. When the
engine publishes an event for a user, we put it on each of that user's queues; the SSE route takes
items off its queue and writes them to the HTTP response as they arrive. The browser's EventSource
receives them instantly — no polling.

Why in-process (no Redis): one server process runs the whole engine, so a dict of queues is enough.
With several servers we'd swap this class for Redis pub/sub (same publish/subscribe methods).
"""
import asyncio
from collections import defaultdict
from typing import Any

MAX_QUEUE = 200


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, user_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE)
        self._subscribers[user_id].add(q)
        return q

    def unsubscribe(self, user_id: int, q: asyncio.Queue) -> None:
        self._subscribers[user_id].discard(q)
        if not self._subscribers[user_id]:
            self._subscribers.pop(user_id, None)

    @property
    def connected(self) -> int:
        return sum(len(qs) for qs in self._subscribers.values())

    def publish(self, user_id: int, event: str, data: dict[str, Any]) -> None:
        """Send one event to every open tab of one user. Slow tabs drop events instead of blocking us."""
        for q in list(self._subscribers.get(user_id, ())):
            try:
                q.put_nowait({"event": event, "data": data})
            except asyncio.QueueFull:
                pass

    def publish_many(self, user_ids: set[int] | list[int], event: str, data: dict[str, Any]) -> None:
        for uid in set(user_ids):
            self.publish(uid, event, data)

    def broadcast(self, event: str, data: dict[str, Any]) -> None:
        """Send to everyone (only used for aggregate, non-private data like queue counts)."""
        for uid in list(self._subscribers):
            self.publish(uid, event, data)


bus = EventBus()
