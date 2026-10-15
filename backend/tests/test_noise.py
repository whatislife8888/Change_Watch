"""
Tests for noise.py: every normalisation rule, sensitivity thresholds, volatile signatures, flapping.
Run: cd backend && .venv/bin/pytest -q
"""
from datetime import date

import pytest

from app import noise

TODAY = date(2026, 10, 15)


def n(text: str, sensitivity: str = "medium") -> str:
    return noise.normalise_line(text, sensitivity, TODAY)


# ---------- dates and times ----------

@pytest.mark.parametrize("text,expected", [
    ("Updated 2026-10-15T10:25:00Z", "Updated <DATE> <TIME>"),
    ("2026-10-15", "<DATE>"),
    ("15 Oct 2026", "<DATE>"),
    ("Oct 15, 2026", "<DATE>"),
    ("October 14th, 2026", "<DATE>"),
    ("15/10/2026", "<DATE>"),
    ("Thursday, 15 Oct", "<DATE> <DATE>"),
    ("at 10:25", "at <TIME>"),
    ("at 10:25:52 AM", "at <TIME>"),
    ("4:15 pm", "<TIME>"),
])
def test_live_dates_and_times_are_normalised(text, expected):
    assert n(text) == expected


@pytest.mark.parametrize("text", [
    "Registrations close 20 Oct",          # a deadline 5 days away is information, not noise
    "Deadline 20/10/2026",
    "Published 3 Mar 2024",
    "Founded on 2001-01-15",
])
def test_far_away_dates_are_kept(text):
    assert n(text) == text


def test_deadline_change_is_still_visible():
    assert n("Registrations close 20 Oct") != n("Registrations close 22 Oct")


# ---------- relative times and countdowns ----------

@pytest.mark.parametrize("text,expected", [
    ("Posted 5 minutes ago", "Posted <RELTIME>"),
    ("2h ago", "<RELTIME>"),
    ("updated 3 days ago", "updated <RELTIME>"),
    ("yesterday", "<RELTIME>"),
    ("just now", "<RELTIME>"),
    ("Sale ends in 13h 33m 52s", "Sale ends in <TIMER>"),
    ("00:12:45 left", "<TIMER> left"),
])
def test_relative_times_and_countdowns(text, expected):
    assert n(text) == expected


# ---------- counters ----------

@pytest.mark.parametrize("text,expected", [
    ("1,234 views", "<COUNT> views"),
    ("12K likes", "<COUNT> likes"),
    ("342 online", "<COUNT> online"),
    ("1.2M followers", "<COUNT> followers"),
    ("(2,341 reviews)", "(<COUNT> reviews)"),
])
def test_engagement_counters(text, expected):
    assert n(text) == expected


def test_counters_kept_on_high_sensitivity():
    assert n("1,234 views", "high") == "1,234 views"


# ---------- tokens ----------

@pytest.mark.parametrize("text,expected", [
    ("id 3f8a9c2e4b1d7f60a9e2", "id <TOKEN>"),
    ("req 123e4567-e89b-12d3-a456-426614174000", "req <TOKEN>"),
    ("app.js?v=123456", "app.js?v=<TOKEN>"),
    ("nonce: AbC123xyz987", "nonce: <TOKEN>"),
    ("sig dGhpc0lzQVRlc3RUb2tlbjEyMzQ1Ng", "sig <TOKEN>"),
])
def test_random_tokens(text, expected):
    assert n(text) == expected


def test_copyright_year():
    assert n("© 2025 ACME Ltd") == "© <YEAR> ACME Ltd"


# ---------- things we must NOT touch ----------

@pytest.mark.parametrize("text", [
    "Price: ₹79,900",
    "$1,234.56",
    "Only 3 left in stock",
    "Page 3 of 10",
    "Version 2.4.1",
])
def test_prices_and_plain_numbers_are_kept(text):
    assert n(text) == text


def test_whitespace_collapsed():
    assert n("  a   b \t c ") == "a b c"


# ---------- normalise_text ----------

def test_normalise_text_keeps_raw_and_norm_aligned():
    out = noise.normalise_text("Hello\nUpdated 10:25\n\nWorld", today=TODAY)
    assert out.raw_lines == ["Hello", "Updated 10:25", "", "World"]
    assert out.norm_lines == ["Hello", "Updated <TIME>", "", "World"]


def test_volatile_text_rule_drops_matching_lines():
    sig = noise.line_signature("Served by node 4812 in 23ms")
    rules = [{"kind": "text", "value": sig}]
    out = noise.normalise_text("Header\nServed by node 911 in 7ms\nFooter", volatile_rules=rules, today=TODAY)
    assert out.raw_lines == ["Header", "Footer"]
    assert out.dropped_by_rules == 1


def test_line_signature():
    assert noise.line_signature("Served by node 4812 in 23ms") == "Served by node # in #ms"
    assert noise.line_signature("Recommended: Supercalifragilistic") == "Recommended: *"


# ---------- sensitivity ----------

def size(old: list[str], new: list[str]) -> noise.ChangeSize:
    return noise.measure_change(old, new)


BASE = ["Line of ordinary page text number %d that pads the page out a bit" % i for i in range(40)]


def test_identical_is_never_significant():
    assert not noise.is_significant(size(BASE, BASE), "high")


def test_high_flags_any_difference():
    new = BASE[:-1] + [BASE[-1] + "!"]
    assert noise.is_significant(size(BASE, new), "high")


def test_medium_ignores_a_one_character_typo():
    new = BASE[:10] + [BASE[10].replace("ordinary", "ordinery")] + BASE[11:]
    assert not noise.is_significant(size(BASE, new), "medium")


def test_medium_flags_a_new_line():
    new = BASE + ["Registrations close 20 Oct"]
    assert noise.is_significant(size(BASE, new), "medium")


def test_low_needs_a_big_change():
    small = BASE + ["Registrations close 20 Oct"]
    assert not noise.is_significant(size(BASE, small), "low")
    big = BASE + ["A whole new paragraph announcing a very important update for every participant " * 3]
    assert noise.is_significant(size(BASE, big), "low")


def test_stricter_levels():
    assert noise.stricter("high") == "medium"
    assert noise.stricter("medium") == "low"
    assert noise.stricter("low") == "low"


# ---------- flapping ----------

def test_oscillation_detected():
    # newest first: baseline B, then A, then B -> new A means A,B,A,B
    assert noise.is_oscillating("A", ["B", "A", "B"])


def test_no_oscillation_for_new_content():
    assert not noise.is_oscillating("C", ["B", "A", "B"])
    assert not noise.is_oscillating("A", ["B"])
