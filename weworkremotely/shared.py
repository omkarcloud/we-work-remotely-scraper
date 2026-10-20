"""Small value and transport helpers the weworkremotely package needs, kept
in the package so it stands alone (the open-source We Work Remotely Scraper
ships this folder verbatim, like greenhouse/shared.py does for Greenhouse).
Pure functions plus a tiny in-process memo; every helper tolerates None and
junk. Copied from greenhouse/shared.py (Cloudflare + memo) and
reed/parsers.py (text helpers) rather than imported, so no other site's
package is needed."""
import html as html_lib
import re
import threading
import time
from collections import OrderedDict

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


# ---- values ------------------------------------------------------------------------------

def to_int(value):
    try:
        return int(value) if value not in (None, "") and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        try:
            return int(float(str(value).replace(",", "")))
        except (TypeError, ValueError):
            return None


def text(value):
    if not isinstance(value, str):
        return None
    value = _WS_RE.sub(" ", html_lib.unescape(value)).strip()
    return value or None


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


def click_turnstile(page):
    """Real mouse click on the Cloudflare Turnstile checkbox, when shown."""
    import random
    for frame in page.frames:
        if not frame.url.startswith("https://challenges.cloudflare.com"):
            continue
        try:
            box = frame.frame_element().bounding_box()
        except Exception:
            box = None
        if not box or box.get("width", 0) < 50:
            continue
        x = box["x"] + box["width"] / 9 + random.uniform(-4, 4)
        y = box["y"] + box["height"] / 2 + random.uniform(-4, 4)
        page.mouse.move(x, y, steps=random.randint(10, 25))
        page.wait_for_timeout(random.randint(100, 300))
        page.mouse.down()
        page.wait_for_timeout(random.randint(50, 150))
        page.mouse.up()
        return True
    return False


# ---- memo -------------------------------------------------------------------------------------

_memo = OrderedDict()
_memo_lock = threading.Lock()
MEMO_TTL = 600
MEMO_MAX = 256


def memoized(key, fn, ttl=MEMO_TTL):
    """fn() memoised in-process for `ttl` seconds under `key`."""
    now = time.monotonic()
    with _memo_lock:
        hit = _memo.get(key)
        if hit and now - hit[0] < ttl:
            _memo.move_to_end(key)
            return hit[1]
    value = fn()
    with _memo_lock:
        _memo[key] = (now, value)
        _memo.move_to_end(key)
        while len(_memo) > MEMO_MAX:
            _memo.popitem(last=False)
    return value
