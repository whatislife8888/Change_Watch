"""
summarize.py — a one-line summary of each change: "3 lines added, 1 removed. New: 'Registrations close 20 Oct'".

Who uses it: checker.py (every new snapshot), alerts.py, rss.py.
The heuristic version needs no API key. The AI version (Anthropic) is added in Phase 9 and falls back
to this one when it's not configured or fails.
"""
import re

INFORMATIVE = re.compile(r"[A-Za-z]{3,}")


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
