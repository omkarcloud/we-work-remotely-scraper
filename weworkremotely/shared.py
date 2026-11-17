"""Small value and transport helpers the weworkremotely package needs, kept in
the package so it needs nothing from another site (the open-source We Work
Remotely Scraper ships this folder verbatim, like greenhouse/shared.py does
for Greenhouse). Pure functions plus a tiny in-process memo; every helper
tolerates None and junk. Copied from greenhouse/shared.py (Cloudflare + memo)
and reed/parsers.py (text helpers) rather than imported, so no other site's
package is needed."""
import html as html_lib
import re
import threading
import time
from collections import OrderedDict
from scraper_utils.values import to_int
from scraper_utils.text import clean as text
from scraper_utils import memo

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


# ---- values ------------------------------------------------------------------------------


def strip_html(value):
    """HTML -> readable plain text (block tags become newlines)."""
    if not isinstance(value, str) or not value.strip():
        return None
    out = re.sub(r"(?i)<\s*br\s*/?>", "\n", value)
    out = re.sub(r"(?i)</\s*(p|div|li|h[1-6]|tr|ul|ol|section|article|header)\s*>", "\n", out)
    out = re.sub(r"(?i)<\s*(p|div|h[1-6]|tr|ul|ol|section|article|header)(\s[^>]*)?>", "\n", out)
    out = re.sub(r"(?i)<\s*li[^>]*>", "\n- ", out)
    out = _TAG_RE.sub("", out)
    out = html_lib.unescape(out)
    lines = [_WS_RE.sub(" ", line).strip() for line in out.splitlines()]
    out = "\n".join(line for line in lines if line)
    return out or None


# ---- Cloudflare ----------------------------------------------------------------------------

CF_MARKERS = ("just a moment", "security check", "attention required", "cf-chl", "challenge-platform")


def is_challenged(status, headers, body):
    """A Cloudflare challenge page."""
    if (headers or {}).get("cf-mitigated") == "challenge":
        return True
    head = (body or "")[:4000].lower()
    return status in (403, 429, 503) and any(m in head for m in CF_MARKERS)


# ---- memo -------------------------------------------------------------------------------------

_memo = OrderedDict()
_memo_lock = threading.Lock()
MEMO_TTL = 600
MEMO_MAX = 256


def memoized(key, fn, ttl=MEMO_TTL):
    """fn() memoised in-process for `ttl` seconds under `key`."""
    return memo.memoized(_memo, _memo_lock, MEMO_MAX, key, fn, ttl)
