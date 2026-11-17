"""We Work Remotely transport: plain curl_cffi with browser-impersonated TLS.
No browser, no login, no token (validated 2026-10-19: every surface below
answered 200 on the first try, an 80-request burst over 8 threads with a
fresh session each time was 80/80).

Egress: in grow every session leaves through a sticky residential proxy exit
(config.weworkremotely_proxy, WEWORKREMOTELY_REQUIRE_PROXY) — weworkremotely.com
is never contacted from the server's own IP; with no proxy the call fails
instead of going direct. A config without WEWORKREMOTELY_REQUIRE_PROXY (the
open-source kit, run on the user's own machine) may go direct.

Cloudflare fronts weworkremotely.com with a MANAGED CHALLENGE for plain
curl's TLS fingerprint (cf-mitigated: challenge, "Just a moment…"); Chrome
TLS passes without any cookie. The RSS feeds are open even to plain curl.

Upstream surfaces (all on https://weworkremotely.com, server-rendered Rails):

  * SEARCH   GET /remote-jobs/search?term=&categories[]=ID&country[]=CC
                 &salary_range[]=<label>&skills[]=ID&sort=<window>&job_filter=<all|hot|boosted>
             Every match on ONE page grouped by category section; each
             section is capped at ~25 cards with a "View all" link while
             `data-job-filter-count` carries the true total. `page=` is
             ignored. The form's option lists (670 skills, 249 countries,
             5 salary buckets) ride along in the page.
  * CATEGORY GET /categories/<site-slug>   the complete list of a category
             (78 of 78 verified), no pagination. MUST be fetched with an
             HTML Accept header: `Accept: */*` makes Rails answer the RSS.
  * LANDING  GET /remote-<region>-jobs, /100-percent-remote-jobs,
             /remote-full-time-jobs, /remote-contract-jobs, /remote-<kw>-jobs,
             /top-trending-remote-jobs: card lists with ?page=N (50/page)
             where the list exceeds a page.
  * JOB      GET /remote-jobs/<slug>: JobPosting JSON-LD + the page (sidebar
             facts, skills, description HTML, company panel, related jobs).
             An unknown slug 302s to the homepage (no 404).
  * COMPANY  GET /company/<slug>: profile card + modal panels + every active
             job. Unknown slug 302s to the homepage.
  * TOP 100  GET /top-remote-companies
  * RSS      GET /remote-jobs.rss, /categories/<site-slug>.rss (region feeds
             exist but half of them 500 server-side, so they are not used).

Block handling is defensive (none was ever seen): a 403 / 429 / challenge
page drops the worker's session, so the retry opens a fresh exit; a page
still blocked after every retry raises WeworkremotelyBlocked.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  WeworkremotelyUpstreamError  transport failure / 5xx            — retryable
  WeworkremotelyBlocked        403 / 429 / challenge page         — retryable on a new exit
  WeworkremotelyBadRequest     params the site cannot serve        — never retried
  WeworkremotelyNotFound       missing entity (redirect home/404)  — never retried
"""
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from weworkremotely.shared import is_challenged
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from scraper_utils import debug, fanout, retry, sessions

SITE = "https://weworkremotely.com"
IMPERSONATE = "chrome"
TIMEOUT = 60
FANOUT_WORKERS = 8

PAGE_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": egress.accept_language(),
    "upgrade-insecure-requests": "1",
}
FEED_HEADERS = {
    "accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": egress.accept_language(),
}


class WeworkremotelyUpstreamError(UpstreamError):
    """Transport failure or 5xx — retryable."""


class WeworkremotelyBlocked(WeworkremotelyUpstreamError, Blocked):
    """403 / 429 or a challenge page — retryable on a fresh exit."""


class WeworkremotelyBadRequest(BadRequest):
    """The site cannot serve these params — never retried."""


class WeworkremotelyNotFound(NotFound):
    """Entity / page does not exist — never retried."""


# ---- sessions ------------------------------------------------------------------
_local = threading.local()


def _proxy_for_new_session():
    """The exit for a new session. Raises when the config requires a proxy
    and none is available (never falls back to the server's own IP)."""
    forced = config.weworkremotely_proxy()
    if forced:
        return forced
    if getattr(config, "WEWORKREMOTELY_REQUIRE_PROXY", False):
        raise WeworkremotelyUpstreamError("no We Work Remotely proxy configured "
                                          "(weworkremotely.com is never contacted from the server's IP)")
    return None


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        proxy = _proxy_for_new_session()
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        _local.session = sess
    return sess


def _drop_session():
    sessions.drop(_local)


def dump_debug(name, text):
    debug.dump("WEWORKREMOTELY_DEBUG_DIR", name, text, encoding="utf-8")


# ---- requests --------------------------------------------------------------------

def _retrying(fn):
    return retry.run(fn, config, WeworkremotelyUpstreamError, lambda e: _drop_session())


def build_url(path, params=None):
    """Path + params -> absolute URL. List values repeat as Rails array
    params (`categories[]=2&categories[]=17`); None / empty are dropped."""
    url = path if path.startswith("http") else SITE + path
    pairs = []
    for key, value in (params or {}).items():
        if value is None or value == "" or value == [] or value is False:
            continue
        if isinstance(value, (list, tuple)):
            name = key if key.endswith("[]") else key + "[]"
            pairs += [(name, str(v)) for v in value if v not in (None, "")]
        else:
            pairs.append((key, "true" if value is True else str(value)))
    if pairs:
        url += ("&" if "?" in url else "?") + urlencode(pairs)
    return url


def _is_home(url):
    parsed = urlparse(url or "")
    return parsed.path in ("", "/") and not parsed.query


def _get(url, headers, label):
    sess = _session()
    try:
        resp = sess.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
    except Exception as e:
        raise WeworkremotelyUpstreamError(f"request failed: {type(e).__name__}: {e}")
    finally:
        sess.cookies.clear()
    status = resp.status_code
    body = resp.text or ""
    resp_headers = {k.lower(): v for k, v in dict(resp.headers).items()}
    if status in (403, 429) or is_challenged(status, resp_headers, body):
        dump_debug("blocked", body)
        raise WeworkremotelyBlocked(f"HTTP {status} on {label}")
    if status in (404, 410):
        return status, body, str(resp.url)
    if status == 400 or status == 406:
        raise WeworkremotelyBadRequest(f"upstream rejected {label}")
    if status != 200:
        raise WeworkremotelyUpstreamError(f"HTTP {status} on {label}")
    return status, body, str(resp.url)


def get_page(path, params=None, *, label=None, must_exist=True):
    """GET one HTML page -> (body, final_url). A 404 or a redirect to the
    homepage (the site's way of saying "no such job / company") raises
    WeworkremotelyNotFound when must_exist. A block that survives every curl
    retry raises WeworkremotelyBlocked."""
    url = build_url(path, params)
    label = label or path

    def once():
        status, body, final = _get(url, PAGE_HEADERS, label)
        if status != 200:
            raise WeworkremotelyNotFound(f"{label} not found")
        if must_exist and _is_home(final) and not _is_home(url):
            raise WeworkremotelyNotFound(f"{label} not found")
        if not body.strip():
            raise WeworkremotelyUpstreamError(f"empty body on {label}")
        if body.lstrip().startswith("<?xml"):
            raise WeworkremotelyUpstreamError(f"{label} answered XML instead of HTML")
        return body, final

    return _retrying(once)


def get_feed(path, *, label=None):
    """GET one RSS feed -> XML text."""
    url = build_url(path)
    label = label or path

    def once():
        status, body, final = _get(url, FEED_HEADERS, label)
        if status != 200 or _is_home(final):
            raise WeworkremotelyNotFound(f"{label} not found")
        if "<rss" not in body[:500] and "<item>" not in body:
            dump_debug("nonrss", body)
            raise WeworkremotelyUpstreamError(f"{label} answered no RSS")
        return body

    return _retrying(once)


# ---- fan-out ------------------------------------------------------------------------
_pool = ThreadPoolExecutor(max_workers=FANOUT_WORKERS, thread_name_prefix="weworkremotely")


def run_parallel(fns):
    return fanout.on_pool(_pool, fns)


def gather(mapping, optional=()):
    """{key: callable} in parallel -> {key: result}. Keys named in `optional`
    yield None instead of failing the set when they raise a scraper error."""
    return fanout.gather_optional(run_parallel, mapping, optional, (UpstreamError, BadRequest, NotFound))


if __name__ == "__main__":
    # Smoke test: python weworkremotely/fetch.py [term]
    term = sys.argv[1] if len(sys.argv) > 1 else "python"
    import re
    body, final = get_page("/remote-jobs/search", {"term": term, "categories": [2, 17, 18]})
    print("search:", final, "cards:", len(re.findall("new-listing-container", body)),
          "count:", re.findall(r"data-job-filter-count>(\d+)<", body))
    slug = re.search(r'href="/remote-jobs/([^"]+)"', body).group(1)
    body, final = get_page(f"/remote-jobs/{slug}")
    print("job:", final, len(body))
    print("feed items:", get_feed("/remote-jobs.rss").count("<item>"))
    try:
        get_page("/remote-jobs/this-job-does-not-exist-xyz")
    except WeworkremotelyNotFound as e:
        print("missing job ->", e)
