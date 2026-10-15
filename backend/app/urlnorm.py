"""
urlnorm.py — turn whatever the user typed into one canonical URL, plus the dial seed and domain.

Who uses it: the watches route (find-or-create a Target), the URL preview endpoint, politeness (domain).
Depends on: tldextract (to find the "registrable domain", e.g. bbc.co.uk rather than www.bbc.co.uk).

Why normalise: "https://Example.com/?utm_source=x" and "example.com" are the same page. If we stored
them separately, two users watching "the same" page would cause two fetches (design question 2).
"""
import hashlib
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

import tldextract


class InvalidURL(ValueError):
    """Raised with a user-friendly message when a URL can't be watched."""


# Query parameters that only track where a click came from; they never change the page content.
TRACKING_PARAMS = {"fbclid", "gclid", "dclid", "msclkid", "ref", "ref_src", "igshid", "mc_cid", "mc_eid", "_ga", "yclid"}
DEFAULT_PORTS = {"http": 80, "https": 443}

# Use the suffix list bundled with the package — never download it at runtime (no network surprises).
_extract = tldextract.TLDExtract(suffix_list_urls=())


def normalise_url(raw: str) -> str:
    """Return the canonical form of a URL, or raise InvalidURL.

    Steps: trim, add https:// if no scheme, allow only http/https, reject user:pass@, lowercase scheme
    and host, drop default ports and #fragments, drop tracking params, sort the remaining query params,
    and strip a trailing slash (except for the root path "/").
    """
    text = (raw or "").strip()
    if not text:
        raise InvalidURL("Paste a link to a page.")
    if " " in text:
        raise InvalidURL("A link can't contain spaces.")
    if "://" not in text:
        text = "https://" + text

    parts = urlsplit(text)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise InvalidURL("Only http and https pages can be watched.")
    if parts.username or parts.password or "@" in parts.netloc:
        raise InvalidURL("Links with a username or password can't be watched. ChangeWatch only checks public pages.")

    host = (parts.hostname or "").lower().rstrip(".")
    if not host or "." not in host and host != "localhost":
        raise InvalidURL("That doesn't look like a web address.")
    try:
        host.encode("idna")
    except UnicodeError as exc:
        raise InvalidURL("That doesn't look like a web address.") from exc

    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidURL("The port number in that link isn't valid.") from exc
    netloc = host if port is None or DEFAULT_PORTS.get(scheme) == port else f"{host}:{port}"

    # Re-quote the path so equivalent spellings ("%7E" vs "~") end up identical.
    path = quote(unquote(parts.path or "/"), safe="/:@!$&'()*+,;=-._~")
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/") or "/"

    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(query_pairs))
    return urlunsplit((scheme, netloc, path, query, ""))


def dial_seed(normalised_url: str) -> str:
    """First 8 hex characters of SHA-256(url). The frontend turns this into the dial's guilloché pattern,
    so the same page always gets the same dial, on every device."""
    return hashlib.sha256(normalised_url.encode("utf-8")).hexdigest()[:8]


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def registrable_domain(url_or_host: str) -> str:
    """The domain a person would register, e.g. 'news.bbc.co.uk' -> 'bbc.co.uk'.

    Why: politeness limits are per site owner, not per subdomain — a.example.com and b.example.com
    usually run on the same servers.
    """
    host = host_of(url_or_host) if "://" in url_or_host else url_or_host.lower()
    ext = _extract(host)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    return host  # IPs, localhost, single-label hosts


def display_domain(url: str) -> str:
    """Host without a leading 'www.' — what we show under each dial."""
    host = host_of(url)
    return host[4:] if host.startswith("www.") else host
