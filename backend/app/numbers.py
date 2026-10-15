"""
numbers.py — pull one number (a price, a count, a percentage) out of a page for tracking (bonus).

Who uses it: checker.py (records a point on every successful check), routes/picker.py (preview).
Depends on: extract.py (CSS selector → element text).

parse_number() handles the formats people actually see:
  ₹1,23,456.50 (Indian lakh grouping)   $1,234.56   1.234,56 € (European)   12K / 1.2M   -4.5%   (1,200)
The decimal separator is decided by the LAST separator in the number: in "1.234,56" the last one is a
comma followed by 2 digits, so the comma is the decimal point; in "1,234.56" it's the dot.
"""
import re

from . import extract

NUMBER = re.compile(r"[-−–]?\(?\s*[₹$€£¥]?\s*\d[\d.,\s  ]*\d?\s*[KkMmBb]?(?:\s*(?:lakh|crore|cr|L))?\s*%?\)?", re.IGNORECASE)
SUFFIX = {"k": 1e3, "m": 1e6, "b": 1e9, "lakh": 1e5, "l": 1e5, "crore": 1e7, "cr": 1e7}


def parse_number(text: str) -> float | None:
    """Parse the first number in `text`. Returns None if there isn't one."""
    if not text:
        return None
    match = NUMBER.search(text)
    if not match:
        return None
    raw = match.group(0)
    stripped = raw.strip()
    # A minus sign, or accounting style "(1,200)", means negative.
    negative = stripped.startswith(("-", "−", "–")) or (stripped.startswith("(") and stripped.endswith(")"))
    lower = raw.lower()
    multiplier = 1.0
    for suffix in ("crore", "lakh", "cr"):
        if suffix in lower:
            multiplier = SUFFIX[suffix]
            break
    else:
        tail = re.search(r"\d\s*([kmb])\b", lower) or re.search(r"\d\s*([kmb])\s*%?\)?$", lower.strip())
        if tail:
            multiplier = SUFFIX[tail.group(1)]
        elif re.search(r"\d\s*l\b", lower):
            multiplier = SUFFIX["l"]
    digits = re.sub(r"[^\d.,]", "", raw)
    if not digits or not any(ch.isdigit() for ch in digits):
        return None
    last_dot, last_comma = digits.rfind("."), digits.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        decimal = "." if last_dot > last_comma else ","
    elif last_comma >= 0:
        # "1,234" (thousands) vs "12,5" (decimal): a decimal comma is followed by 1–2 digits only once.
        after = digits[last_comma + 1:]
        decimal = "," if len(after) in (1, 2) and digits.count(",") == 1 else None
    elif last_dot >= 0:
        after = digits[last_dot + 1:]
        decimal = None if len(after) == 3 and digits.count(".") > 1 else "."
    else:
        decimal = None
    if decimal == ",":
        cleaned = digits.replace(".", "").replace(",", ".")
    elif decimal == ".":
        cleaned = digits.replace(",", "")
    else:
        cleaned = digits.replace(",", "").replace(".", "")
    try:
        value = float(cleaned) * multiplier
    except ValueError:
        return None
    return -value if negative else value


def extract_number(html: str, selector: str | None, regex: str | None) -> tuple[float, str] | None:
    """Find the tracked number: CSS selector first (its text), then an optional regex with one group."""
    text = ""
    if selector:
        soup = extract.parse(html)
        try:
            found = soup.select(selector)
        except Exception:
            found = []
        if found:
            text = extract.element_text(found[0])
    if regex:
        try:
            pattern = re.compile(regex, re.IGNORECASE)
        except re.error:
            pattern = None
        if pattern:
            haystack = text or extract.element_text(extract.parse(html).body or extract.parse(html))
            m = pattern.search(haystack)
            if m:
                text = m.group(1) if m.groups() else m.group(0)
    if not text:
        return None
    value = parse_number(text)
    if value is None:
        return None
    return value, text.strip()[:80]
