"""
noise.py — everything that stops ChangeWatch from crying wolf (requirement 4 + design question 3).

Who uses it: checker.py (normalise text before hashing, decide if a change is significant, learn
volatile rules, detect flapping), extract.py (structural noise selectors), routes (to show the rules).
Depends on: nothing but the standard library (re, difflib) — easy to unit-test.

The layers, in the order they run:
1. Structural removal (NOISE_SELECTORS): cookie banners, ads, chat widgets, carousels are cut out of
   the HTML before we even read the text (applied in extract.py).
2. Text normalisation (RULES): times, live dates (within 2 days of the check), relative times,
   countdowns, view/like counters and random tokens are replaced with placeholders like <TIME>, so
   "Updated 10:25" and "Updated 10:26" hash the same. Prices and plain numbers are left alone.
3. Volatile rules (learned per page): lines that differed between two fetches 10 s apart are dropped.
4. Significance (is_significant): the remaining difference must be big enough for the sensitivity.
5. Flapping guard: a page that keeps flipping gets its sensitivity raised for 24 hours.
"""
import difflib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable

# ---------------------------------------------------------------------------
# 1. Structural noise: CSS selectors removed from the page before text extraction.
# ---------------------------------------------------------------------------

NOISE_SELECTORS: dict[str, list[str]] = {
    "Cookie and consent banners": [
        '[id*="cookie" i]', '[class*="cookie" i]', '[id*="consent" i]', '[class*="consent" i]', '[class*="gdpr" i]',
    ],
    "Ads": [
        '[id^="ad-" i]', '[class*="advert" i]', '[class*="ad-slot" i]', "ins.adsbygoogle", "[data-ad]", '[id*="google_ads"]',
    ],
    "Chat widgets": [
        '[id*="intercom"]', '[class*="crisp"]', '[id*="hubspot"]', '[class*="chat-widget" i]',
    ],
}

CAROUSEL_SELECTORS: list[str] = [
    '[class*="carousel" i]', '[class*="slider" i]', '[class*="marquee" i]', '[class*="ticker" i]',
    ".swiper", ".slick-slider", '[role="marquee"]',
]


def builtin_selectors(ignore_carousels: bool) -> list[str]:
    """Every built-in noise selector that applies to a watch."""
    out = [sel for group in NOISE_SELECTORS.values() for sel in group]
    if ignore_carousels:
        out += CAROUSEL_SELECTORS
    return out


def builtin_selector_groups() -> dict[str, list[str]]:
    """For the UI's read-only "built-in noise filters" list."""
    return {**NOISE_SELECTORS, "Rotating banners and carousels (unless turned off)": CAROUSEL_SELECTORS}


# ---------------------------------------------------------------------------
# 2. Text normalisation rules.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    """One normalisation rule: a regex and what to replace matches with.

    replacement: a string (may use \\1 group references) or a function(match, today) -> str.
    skip_on_high: engagement counters are kept when sensitivity is "high" (the user wants everything).
    """
    name: str
    pattern: re.Pattern
    replacement: str | Callable[[re.Match, date], str]
    skip_on_high: bool = False


MONTHS = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
WEEKDAYS = r"(?:Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|Thu(?:rs(?:day)?)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)"
MONTH_NUMBERS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
I = re.IGNORECASE

# How close to the check date a date must be to count as a "live" timestamp (noise).
NEAR_DAYS = 2


def _near(candidates: list[tuple[int, int, int]], today: date) -> bool:
    """True if any (year, month, day) candidate is a real date within NEAR_DAYS of today."""
    for y, m, d in candidates:
        try:
            if abs((date(y, m, d) - today).days) <= NEAR_DAYS:
                return True
        except ValueError:
            continue
    return False


def _date_if_near(build: Callable[[re.Match, date], list[tuple[int, int, int]]]) -> Callable[[re.Match, date], str]:
    """Make a replacement function: '<DATE>' when the matched date is within 2 days of the check, else unchanged.

    Why date-aware: "Updated 15 Oct 2026" (today) is a live timestamp — noise. But "Registrations close
    20 Oct" is information users care about; if we blanked every date, a deadline change would be invisible.
    """
    def replace(match: re.Match, today: date) -> str:
        try:
            candidates = build(match, today)
        except (ValueError, KeyError, TypeError):
            return match.group(0)
        return "<DATE>" if _near(candidates, today) else match.group(0)
    return replace


def _year(text: str) -> int:
    y = int(text)
    return y + 2000 if y < 100 else y


def _month(name: str) -> int:
    return MONTH_NUMBERS[name[:3].lower()]


def _iso(m: re.Match, today: date) -> list[tuple[int, int, int]]:
    y, mo, d = m.group("iso").split("-")
    return [(int(y), int(mo), int(d))]


def _dmy(m: re.Match, today: date) -> list[tuple[int, int, int]]:
    return [(_year(m.group("y")), _month(m.group("mon")), int(m.group("d")))]


def _numeric(m: re.Match, today: date) -> list[tuple[int, int, int]]:
    a, b, y = int(m.group("a")), int(m.group("b")), _year(m.group("y"))
    return [(y, b, a), (y, a, b)]  # 15/10/2026 (day first, as in India) or 10/15/2026 (US)


def _dm(m: re.Match, today: date) -> list[tuple[int, int, int]]:
    mon = m.group("mon") or m.group("mon2")
    day = m.group("d") or m.group("d2")
    return [(today.year + dy, _month(mon), int(day)) for dy in (-1, 0, 1)]


# Order matters: more specific patterns (ISO datetimes, countdowns) run before generic ones (times).
RULES: list[Rule] = [
    # Random tokens first, so their digits aren't mistaken for dates or counters.
    Rule("uuid", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", I), "<TOKEN>"),
    Rule("cache_buster", re.compile(r"([?&](?:v|ver|version|cb|t|ts|_|nonce|token|sid|session|sessionid)=)[\w.-]+", I), r"\1<TOKEN>"),
    Rule("labelled_token", re.compile(r"\b((?:nonce|token|session(?:\s*id)?|request\s*id|csrf|trace\s*id|build)\s*[:=#]?\s*)[A-Za-z0-9_\-+/=]{6,}", I), r"\1<TOKEN>"),
    Rule("hex_token", re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{16,}\b", I), "<TOKEN>"),
    Rule("base64_token", re.compile(r"(?<![\w/+])(?=[A-Za-z0-9+/_-]*\d)(?=[A-Za-z0-9+/_-]*[A-Z])(?=[A-Za-z0-9+/_-]*[a-z])[A-Za-z0-9+/_-]{24,}={0,2}(?![\w/+])"), "<TOKEN>"),

    # Countdowns and times (always noise: a clock on a page changes every load).
    Rule("iso_time_part", re.compile(r"(?<=\d)[T ](\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)\b"), " <TIME>"),
    Rule("countdown_hms", re.compile(r"\b\d{1,3}\s*h(?:ours?|rs?)?\s*\d{1,2}\s*m(?:in(?:utes?)?)?\s*(?:\d{1,2}\s*s(?:ec(?:onds?)?)?)?\b", I), "<TIMER>"),
    Rule("countdown_days", re.compile(r"\b\d{1,3}\s*d(?:ays?)?\s+\d{1,2}\s*h(?:ours?)?(?:\s*\d{1,2}\s*m(?:in)?)?\b", I), "<TIMER>"),
    Rule("time_ampm", re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AaPp]\.?[Mm]\.?)(?!\w)"), "<TIME>"),
    Rule("timer_hhmmss", re.compile(r"\b\d{1,2}:\d{2}:\d{2}\b"), "<TIMER>"),
    Rule("time_24h", re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b"), "<TIME>"),

    # Dates: blanked only when they are within 2 days of the check (a live "updated" stamp).
    Rule("iso_date", re.compile(r"\b(?P<iso>\d{4}-\d{2}-\d{2})\b"), _date_if_near(_iso)),
    Rule("day_month_year", re.compile(rf"\b(?P<d>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<mon>{MONTHS})\.?,?\s+(?P<y>\d{{4}})\b", I), _date_if_near(_dmy)),
    Rule("month_day_year", re.compile(rf"\b(?P<mon>{MONTHS})\.?\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<y>\d{{4}})\b", I), _date_if_near(_dmy)),
    Rule("numeric_date", re.compile(r"\b(?P<a>\d{1,2})[/.](?P<b>\d{1,2})[/.](?P<y>\d{4}|\d{2})\b"), _date_if_near(_numeric)),
    Rule("day_month", re.compile(rf"\b(?P<d>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<mon>{MONTHS})\b|\b(?P<mon2>{MONTHS})\s+(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\b", I), _date_if_near(_dm)),
    Rule("weekday", re.compile(rf"\b{WEEKDAYS}\b,?", I), "<DATE>"),

    # Relative times.
    Rule("relative_ago", re.compile(r"\b(?:about\s+|over\s+|almost\s+)?(?:\d+|an?|one|a\s+few)\s*(?:s|sec|secs|seconds?|m|min|mins|minutes?|h|hr|hrs|hours?|d|days?|w|wk|weeks?|mo|months?|y|yr|years?)\s+ago\b", I), "<RELTIME>"),
    Rule("relative_words", re.compile(r"\b(?:just now|yesterday|today|moments? ago|a moment ago|right now)\b", I), "<RELTIME>"),

    # Copyright years.
    Rule("copyright", re.compile(r"(©|\(c\)|copyright)\s*(\d{4})(?:\s*[-–]\s*\d{4})?", I), r"\1 <YEAR>"),

    # Engagement counters: replace the number, keep the word ("1,234 views" -> "<COUNT> views").
    Rule("counter_paren", re.compile(r"\((\d[\d,.]*[KkMm]?)\s+(reviews?|ratings?|votes?|comments?)\)", I), r"(<COUNT> \2)", skip_on_high=True),
    Rule("counter", re.compile(r"(?<![\w₹$€£.,<])\d[\d,.]*(?:\s?[KkMmBb]\b)?\+?(?=\s*(?:views?|likes?|followers?|following|subscribers?|online|watching|reviews?|ratings?|comments?|shares?|reads?|downloads?|stars?|people|users|visitors|members|votes?|reactions?|retweets?|replies|clicks|plays|listeners)\b)", I), "<COUNT>", skip_on_high=True),
]

WHITESPACE = re.compile(r"\s+")


def normalise_line(line: str, sensitivity: str = "medium", today: date | None = None) -> str:
    """Apply every rule to one line of text, then collapse whitespace.

    `today` is the date of the check (UTC). Tests pass it explicitly so results don't depend on the clock.
    """
    today = today or datetime.now(timezone.utc).date()
    out = line
    for rule in RULES:
        if rule.skip_on_high and sensitivity == "high":
            continue
        if callable(rule.replacement):
            fn = rule.replacement
            out = rule.pattern.sub(lambda m, fn=fn: fn(m, today), out)
        else:
            out = rule.pattern.sub(rule.replacement, out)
    return WHITESPACE.sub(" ", out).strip()


# ---------------------------------------------------------------------------
# 3. Volatile (learned) rules.
# ---------------------------------------------------------------------------

LONG_WORD = re.compile(r"[A-Za-z_\-]{14,}")
DIGITS = re.compile(r"\d+")


def line_signature(line: str) -> str:
    """A fuzzy fingerprint of a line: digit runs -> '#', very long words -> '*'.

    Two lines like "Served by node 4812 in 23ms" and "Served by node 911 in 7ms" share the signature
    "Served by node # in #ms", so one learned rule catches every future variant.
    """
    sig = DIGITS.sub("#", line)
    sig = LONG_WORD.sub("*", sig)
    return WHITESPACE.sub(" ", sig).strip()


@dataclass
class NormalisedText:
    """Raw display lines and their normalised twins, kept 1:1 so diffs can show raw text."""
    raw_lines: list[str]
    norm_lines: list[str]
    dropped_by_rules: int = 0
    rule_hits: dict[str, int] = field(default_factory=dict)

    @property
    def raw_text(self) -> str:
        return "\n".join(self.raw_lines)

    @property
    def norm_text(self) -> str:
        return "\n".join(self.norm_lines)


def normalise_text(text: str, sensitivity: str = "medium", volatile_rules: list[dict] | None = None,
                   today: date | None = None) -> NormalisedText:
    """Normalise every line and drop lines that match a learned text-signature rule.

    Returns both the raw lines (shown to users in diffs) and the normalised lines (hashed and compared),
    aligned 1:1 — line 7 of one is line 7 of the other.
    """
    text_sigs = {r["value"]: r for r in (volatile_rules or []) if r.get("kind") == "text"}
    raw_out: list[str] = []
    norm_out: list[str] = []
    hits: dict[str, int] = {}
    dropped = 0
    for raw in text.split("\n"):
        raw_clean = WHITESPACE.sub(" ", raw).strip()
        if not raw_clean:
            # Keep single blank separators between watched blocks.
            if raw_out and raw_out[-1] != "":
                raw_out.append("")
                norm_out.append("")
            continue
        norm = normalise_line(raw_clean, sensitivity, today)
        if text_sigs:
            sig = line_signature(norm)
            if sig in text_sigs:
                dropped += 1
                hits[sig] = hits.get(sig, 0) + 1
                continue
        raw_out.append(raw_clean)
        norm_out.append(norm)
    while raw_out and raw_out[-1] == "":
        raw_out.pop()
        norm_out.pop()
    return NormalisedText(raw_out, norm_out, dropped, hits)


# ---------------------------------------------------------------------------
# 4. Significance (sensitivity thresholds).
# ---------------------------------------------------------------------------

@dataclass
class ChangeSize:
    """How big a change is, measured on normalised lines."""
    changed_chars: int
    total_chars: int
    added_lines: list[str]
    removed_lines: list[str]
    longest_whole_line: int

    @property
    def score(self) -> float:
        """Fraction of characters that changed (0..1)."""
        return self.changed_chars / max(1, self.total_chars)

    @property
    def is_empty(self) -> bool:
        return self.changed_chars == 0 and not self.added_lines and not self.removed_lines


def measure_change(old_lines: list[str], new_lines: list[str]) -> ChangeSize:
    """Count changed characters and whole added/removed lines between two versions.

    Lines that were *edited* (paired in a replace block) count only the characters that actually
    differ, using a character-level SequenceMatcher. Unpaired lines count in full.
    """
    sm = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    changed = 0
    added: list[str] = []
    removed: list[str] = []
    longest_whole = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        old_block, new_block = old_lines[i1:i2], new_lines[j1:j2]
        pairs = min(len(old_block), len(new_block)) if tag == "replace" else 0
        for k in range(pairs):
            a, b = old_block[k], new_block[k]
            cm = difflib.SequenceMatcher(None, a, b, autojunk=False)
            same = sum(block.size for block in cm.get_matching_blocks())
            changed += (len(a) - same) + (len(b) - same)
            removed.append(a)
            added.append(b)
        for line in old_block[pairs:]:
            changed += len(line)
            removed.append(line)
            longest_whole = max(longest_whole, len(line))
        for line in new_block[pairs:]:
            changed += len(line)
            added.append(line)
            longest_whole = max(longest_whole, len(line))
    total = sum(len(x) for x in old_lines) + sum(len(x) for x in new_lines)
    return ChangeSize(changed, total, added, removed, longest_whole)


SENSITIVITY_ORDER = ["high", "medium", "low"]


def stricter(sensitivity: str) -> str:
    """One level less sensitive (used by the flapping guard): high -> medium -> low."""
    i = SENSITIVITY_ORDER.index(sensitivity) if sensitivity in SENSITIVITY_ORDER else 1
    return SENSITIVITY_ORDER[min(i + 1, len(SENSITIVITY_ORDER) - 1)]


def is_significant(size: ChangeSize, sensitivity: str) -> bool:
    """Apply the sensitivity thresholds from the spec.

    high:   any non-empty difference
    medium: (>= 20 changed chars OR a whole added/removed line of >= 5 chars) AND score >= 0.1%
    low:    >= 100 changed chars AND score >= 2%
    """
    if size.is_empty:
        return False
    if sensitivity == "high":
        return True
    if sensitivity == "low":
        return size.changed_chars >= 100 and size.score >= 0.02
    return (size.changed_chars >= 20 or size.longest_whole_line >= 5) and size.score >= 0.001


# ---------------------------------------------------------------------------
# 5. Flapping.
# ---------------------------------------------------------------------------

def is_oscillating(new_hash: str, recent_hashes: list[str]) -> bool:
    """A→B→A→B detection. `recent_hashes` is newest first (the current baseline is index 0).

    The page is flapping if the new version equals the one from two snapshots ago AND the baseline
    equals the one from three snapshots ago — i.e. it keeps switching between the same two versions.
    """
    if len(recent_hashes) < 3:
        return False
    return new_hash == recent_hashes[1] and recent_hashes[0] == recent_hashes[2]
