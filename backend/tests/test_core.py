"""
Tests for URL normalisation, the SSRF guard, the text differ, number parsing, keyword hits,
extraction and the visual diff's shift detection.
"""
import asyncio

import pytest
from PIL import Image, ImageDraw

from app import differ, extract, numbers, security, summarize, visual_diff
from app.checker import keyword_hit
from app.fetcher import Fetcher, parse_retry_after
from app.urlnorm import InvalidURL, dial_seed, normalise_url, registrable_domain


# ---------- URL normalisation ----------

@pytest.mark.parametrize("raw,expected", [
    ("example.com", "https://example.com/"),
    ("HTTPS://Example.COM:443/Path/?b=2&a=1#frag", "https://example.com/Path?a=1&b=2"),
    ("http://example.com:80/", "http://example.com/"),
    ("https://example.com/page/?utm_source=x&utm_medium=y&fbclid=z&gclid=1&ref=hn", "https://example.com/page"),
    ("https://example.com/a/b/", "https://example.com/a/b"),
    ("https://example.com/%7Euser", "https://example.com/~user"),
])
def test_normalise_url(raw, expected):
    assert normalise_url(raw) == expected


def test_tracking_variants_share_one_target():
    a = normalise_url("https://shop.example.com/item?id=5&utm_campaign=diwali")
    b = normalise_url("shop.example.com/item?utm_source=mail&id=5")
    assert a == b
    assert dial_seed(a) == dial_seed(b) and len(dial_seed(a)) == 8


@pytest.mark.parametrize("raw", ["ftp://example.com", "http://user:pass@site.com", "javascript:alert(1)", "", "not a url"])
def test_invalid_urls(raw):
    with pytest.raises(InvalidURL):
        normalise_url(raw)


def test_registrable_domain():
    assert registrable_domain("https://news.bbc.co.uk/x") == "bbc.co.uk"
    assert registrable_domain("https://a.b.example.com") == "example.com"


# ---------- SSRF guard ----------

@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "172.16.0.1", "169.254.169.254", "::1", "0.0.0.0",
                                "224.0.0.1", "::ffff:10.0.0.1", "100.64.0.1"])
def test_private_ips_rejected(ip):
    assert not security.is_public_ip(ip)


@pytest.mark.parametrize("ip", ["93.184.216.34", "8.8.8.8", "2606:4700:4700::1111"])
def test_public_ips_allowed(ip):
    assert security.is_public_ip(ip)


@pytest.mark.parametrize("url", ["http://localhost/", "http://127.0.0.1/admin", "http://192.168.0.10/", "http://169.254.169.254/latest/meta-data/",
                                 "http://[::1]/", "http://router.local/"])
def test_check_url_rejects_private(url):
    with pytest.raises(security.UnsafeURL):
        asyncio.run(security.check_url_is_public(url))


def test_subrequest_filter_blocks_metadata_ip():
    assert asyncio.run(security.is_allowed_subrequest("http://169.254.169.254/latest", False)) is False
    assert asyncio.run(security.is_allowed_subrequest("data:image/png;base64,AAAA", False)) is True


# ---------- text diff ----------

def test_word_level_replace():
    d = differ.diff_lines(["Price: ₹79,900"], ["Price: ₹74,900"])
    assert d["ops"][0]["type"] == "replace"
    pair = d["ops"][0]["pairs"][0]
    assert ["delete", "₹79,900"] in pair["old"] and ["insert", "₹74,900"] in pair["new"]
    assert d["stats"]["changed"] == 1


def test_insert_and_delete_counts():
    d = differ.diff_lines(["a", "b", "c"], ["a", "c", "d"])
    assert d["stats"]["added"] == 1 and d["stats"]["removed"] == 1


def test_noise_lines_shown_raw_but_not_highlighted():
    d = differ.diff_lines(["Updated <TIME>", "Body"], ["Updated <TIME>", "Body"], ["Updated 10:25", "Body"], ["Updated 10:26", "Body"])
    assert [op["type"] for op in d["ops"]] == ["equal"]
    assert d["ops"][0]["lines"][0] == "Updated 10:26"


def test_preview_lines():
    d = differ.diff_lines(["a"], ["a", "New line here"])
    assert differ.changed_lines_preview(d) == [("+", "New line here")]


# ---------- numbers ----------

@pytest.mark.parametrize("text,value", [
    ("₹1,23,456.50", 123456.50),
    ("$1,234.56", 1234.56),
    ("1.234,56 €", 1234.56),
    ("12K", 12000),
    ("1.2M followers", 1_200_000),
    ("-4.5%", -4.5),
    ("Price: ₹79,900", 79900),
    ("£51.77", 51.77),
    ("In stock (22 available)", 22),
])
def test_parse_number(text, value):
    assert numbers.parse_number(text) == pytest.approx(value)


def test_parse_number_none():
    assert numbers.parse_number("no digits here") is None


def test_extract_number_by_selector():
    html = "<html><body><p class='price'>Now ₹74,900</p></body></html>"
    assert numbers.extract_number(html, ".price", None) == (74900.0, "Now ₹74,900")


# ---------- keywords ----------

def test_keyword_modes():
    assert keyword_hit("appear", ["admit card"], "Results soon", "Admit card released", ["Admit card released"], []) == "admit card"
    assert keyword_hit("disappear", ['"sold out"'], "Status: Sold out", "Status: In stock", ["Status: In stock"], ["Status: Sold out"]) == "sold out"
    assert keyword_hit("any", ["deadline"], "x", "y", ["The deadline moved"], []) == "deadline"
    assert keyword_hit("appear", ["admit card"], "Admit card", "Admit card v2", ["Admit card v2"], []) is None
    assert keyword_hit("off", ["x"], "", "x", ["x"], []) is None


# ---------- extraction ----------

HTML = """<html><head><title>T</title><style>.x{}</style></head><body>
<div id="cookie-banner">We use cookies</div>
<nav>Menu</nav>
<div class="carousel">Promo A</div>
<main><h1>Title</h1><p>Hello <b>world</b></p><p class="ad-slot">Buy now</p>
<ul><li>One</li><li>Two</li></ul><img alt="Logo of ACME" src="x.png"><span hidden>secret</span></main>
<script>var a = 1;</script></body></html>"""


def test_extract_whole_page_removes_noise():
    out = extract.extract(HTML, [], [], True).text
    assert "Hello world" in out and "One" in out and "Logo of ACME" in out
    for gone in ("cookies", "Promo A", "Buy now", "secret", "var a"):
        assert gone not in out


def test_extract_keeps_carousel_when_asked():
    assert "Promo A" in extract.extract(HTML, [], [], False).text


def test_extract_watch_and_ignore_selectors():
    out = extract.extract(HTML, ["main"], ["ul"], True)
    assert "Title" in out.text and "One" not in out.text and "Menu" not in out.text
    missing = extract.extract(HTML, ["#nope"], [], True)
    assert missing.missing_selectors == ["#nope"]


def test_css_path_prefers_stable_id():
    soup = extract.parse("<body><div id='news'><p>a</p><p>b</p></div></body>")
    second_p = soup.select("p")[1]
    assert extract.css_path(second_p) == "#news > p:nth-of-type(2)"


# ---------- summary ----------

def test_heuristic_summary_quotes_informative_line():
    s = summarize.heuristic_summary(["ok", "Registrations close 20 Oct for all teams"], ["Old line"])
    assert s.startswith("2 lines added, 1 removed.") and "Registrations close 20 Oct" in s


# ---------- visual diff ----------

def _page(shift: int, tmp_path, name: str):
    img = Image.new("RGB", (400, 1200), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((20, 20, 380, 60), fill="black")  # header
    if shift:
        d.rectangle((20, 100, 380, 100 + shift - 10), fill="red")  # inserted block
    for i in range(10):
        y = 120 + shift + i * 90
        d.rectangle((20, y, 300, y + 40), fill=(40, 40 + i * 15, 90))
    path = tmp_path / name
    img.save(path)
    return path


def test_shift_detection_aligns_moved_content(tmp_path):
    before = _page(0, tmp_path, "a.png")
    after = _page(80, tmp_path, "b.png")
    result, _ = visual_diff.compare_images(before, after)
    assert result.shifted_by_px == pytest.approx(80, abs=8)
    # Only the inserted block should be flagged, not the whole moved page below it.
    assert result.changed_percent < 25


def test_identical_screenshots_have_no_regions(tmp_path):
    a = _page(0, tmp_path, "a.png")
    result, _ = visual_diff.compare_images(a, a)
    assert result.regions == [] and result.changed_percent == 0


# ---------- fetch classification (design question 1) ----------


@pytest.mark.parametrize("status,outcome,retryable", [
    (200, None, None), (301, None, None), (404, "error", False), (410, "error", False), (500, "error", True),
    (503, "error", True), (401, "blocked", False), (403, "blocked", False), (429, "blocked", True), (400, "error", False),
])
def test_status_classification(status, outcome, retryable):
    result = Fetcher._classify_status("https://e.com", status, {})
    if outcome is None:
        assert result is None
    else:
        assert result.outcome == outcome and result.retryable == retryable


def test_retry_after_seconds():
    assert parse_retry_after("120") == 120
    assert parse_retry_after(None) is None


@pytest.mark.parametrize("title,bot,blocked", [
    ("Just a moment...", {"textLength": 200, "sample": ""}, True),
    ("Attention Required! | Cloudflare", {"textLength": 900, "sample": ""}, True),
    ("Shop", {"strong": True, "textLength": 400, "sample": ""}, True),
    ("Login", {"weak": True, "textLength": 300, "sample": ""}, True),
    ("Big news site", {"weak": True, "textLength": 25000, "sample": "please solve the captcha to comment"}, False),
    ("Blog", {"textLength": 5000, "sample": "welcome"}, False),
])
def test_bot_wall_detection(title, bot, blocked):
    assert Fetcher._looks_like_bot_wall(title, bot) is blocked


def test_demo_paths_whitelisted_only_on_own_host():
    assert security.is_demo_url("http://localhost:8000/demo/bot-check")
    assert not security.is_demo_url("http://localhost:8000/admin")
    assert not security.is_demo_url("http://evil.example/demo/changing-page")
