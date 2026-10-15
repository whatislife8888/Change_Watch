"""
summarize.py — a one-line summary of each change (bonus feature).

Who uses it: checker.py (every real change, never for ignored ones), alerts.py, rss.py.
Depends on: httpx (raw HTTP call to Anthropic's Messages API, as the spec asks), config.

Two ways to summarise:
1. heuristic_summary() — always available, no API key: "3 lines added, 1 removed. New: 'Registrations close 20 Oct'".
2. ai_summary() — if ANTHROPIC_API_KEY is set: we send the page name, URL and the changed lines to Claude
   and ask for one plain sentence under 20 words, e.g. "Price of the iPhone 16 dropped from ₹79,900 to ₹74,900."
   Any failure (timeout, refusal, bad response) falls back to the heuristic — alerts never wait on it.
"""
import logging
import re

import httpx

from .config import settings

log = logging.getLogger("changewatch.summarize")

INFORMATIVE = re.compile(r"[A-Za-z]{3,}")
API_URL = "https://api.anthropic.com/v1/messages"
MAX_DIFF_CHARS = 4000


def _score(line: str) -> float:
    """How informative a line is: prefer real words and numbers, medium length, not menus."""
    words = len(INFORMATIVE.findall(line))
    digits = sum(ch.isdigit() for ch in line)
    length = len(line)
    score = words * 2 + min(digits, 8)
    if length < 8:
        score -= 6
    if length > 160:
        score -= (length - 160) / 20
    return score


def _quote(line: str, limit: int = 80) -> str:
    line = line.strip()
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


def heuristic_summary(added: list[str], removed: list[str]) -> str:
    """Count lines and quote the most informative new (or removed) line."""
    a, r = len(added), len(removed)
    parts = []
    if a:
        parts.append(f"{a} line{'s' if a != 1 else ''} added")
    if r:
        parts.append(f"{r} removed" if a else f"{r} line{'s' if r != 1 else ''} removed")
    head = ", ".join(parts) if parts else "Small change"
    candidates = [x for x in added if x.strip()]
    if candidates:
        best = max(candidates, key=_score)
        return f"{head}. New: '{_quote(best)}'"
    gone = [x for x in removed if x.strip()]
    if gone:
        best = max(gone, key=_score)
        return f"{head}. Removed: '{_quote(best)}'"
    return head + "."


def _diff_text(added: list[str], removed: list[str]) -> str:
    lines = [f"- {x}" for x in removed] + [f"+ {x}" for x in added]
    text = "\n".join(lines)
    return text if len(text) <= MAX_DIFF_CHARS else text[:MAX_DIFF_CHARS] + "\n…"


def _request_body(page_name: str, url: str, added: list[str], removed: list[str]) -> dict:
    prompt = (
        f"A web page changed. Page: {page_name}\nURL: {url}\n\n"
        f"Changed lines ('-' removed, '+' added):\n{_diff_text(added, removed)}\n\n"
        "Write ONE plain sentence under 20 words saying what changed, for a notification. "
        "Be specific with names, numbers and dates, e.g. \"Price of the iPhone 16 dropped from ₹79,900 to ₹74,900.\" "
        "Reply with the sentence only."
    )
    body: dict = {"model": settings.ai_model, "messages": [{"role": "user", "content": prompt}]}
    if settings.ai_model.startswith("claude-haiku"):
        # Haiku thinks by default; thinking tokens would eat this tiny budget. Disabling is allowed at its
        # default effort, and a one-sentence summary doesn't need reasoning.
        body["max_tokens"] = 80
        body["thinking"] = {"type": "disabled"}
    else:
        # Other models may not allow thinking to be disabled: keep effort low and leave room for it.
        body["max_tokens"] = 1024
        body["output_config"] = {"effort": "low"}
    return body


async def ai_summary(page_name: str, url: str, added: list[str], removed: list[str]) -> str | None:
    """Ask Claude for a one-sentence summary. Returns None if not configured or anything goes wrong."""
    if not settings.ai_configured or not (added or removed):
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(API_URL, json=_request_body(page_name, url, added, removed), headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            })
        if r.status_code != 200:
            log.warning("AI summary failed: HTTP %s %s", r.status_code, r.text[:200])
            return None
        data = r.json()
        if data.get("stop_reason") == "refusal":
            return None
        text = " ".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text").strip()
        text = text.strip().strip('"').splitlines()[0].strip() if text else ""
        return text[:200] or None
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
        log.warning("AI summary failed: %s", exc)
        return None
