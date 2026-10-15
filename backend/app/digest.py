"""
digest.py — the daily digest task. Implemented fully in Phase 7; the loop is already scheduled.
"""
import asyncio


async def digest_loop() -> None:
    while True:
        await asyncio.sleep(600)
