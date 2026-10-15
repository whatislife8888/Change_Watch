"""
alerts.py — sending alerts (email, Telegram, Discord). Implemented fully in Phase 7.

The checker already calls these entry points at the right moments; until Phase 7 they only log.
"""
import logging

log = logging.getLogger("changewatch.alerts")


async def on_change(watch: dict, snapshot: dict, previous_snapshot_id: int | None, preview: list[tuple[str, str]]) -> None:
    log.info("Change on watch %s (snapshot %s)", watch["id"], snapshot["id"])


async def on_status(watch: dict, status: str, message: str) -> None:
    log.info("Status %s on watch %s: %s", status, watch["id"], message)


async def on_flapping(watch: dict) -> None:
    log.info("Watch %s is flapping", watch["id"])


async def on_threshold(watch: dict, kind: str, value: float, raw: str) -> None:
    log.info("Threshold %s on watch %s: %s", kind, watch["id"], raw)
