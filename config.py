"""Configuration for the We Work Remotely Scraper. Everything can be set with
an environment variable; the defaults work out of the box.

    PORT                  port the API listens on (default 8000)
    WEWORKREMOTELY_PROXY  proxy URL for every request, e.g.
                          http://user:pass@host:port (default: none — direct).
                          weworkremotely.com answered every page on the first
                          try from one IP, and an 80-request burst over 8
                          threads came back 80/80, so you very likely don't
                          need this. Set it only if you start seeing 403 / 429
                          at high volume.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

# Block fallback: after a 403 / 429 new sessions may switch to a separate
# proxy for WEWORKREMOTELY_BLOCK_COOLDOWN seconds. Off here — with
# WEWORKREMOTELY_PROXY set every request already goes through it.
WEWORKREMOTELY_BLOCK_COOLDOWN = 900

# A page that is still Cloudflare-challenged after every retry can be opened
# in a real Chrome. Off here: this package ships no browser, and plain HTTP
# with Chrome's TLS fingerprint passes on its own.
WEWORKREMOTELY_BROWSER_FALLBACK = False
WEWORKREMOTELY_BROWSER_TIMEOUT = 45


def weworkremotely_proxy():
    """Proxy URL for a new session (None = direct)."""
    return os.environ.get("WEWORKREMOTELY_PROXY") or None


def weworkremotely_fallback_proxy():
    """Proxy for a blocked worker (None = no fallback; see above)."""
    return None
