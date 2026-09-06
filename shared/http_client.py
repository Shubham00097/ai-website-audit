"""
shared/http_client.py

Centralised HTTP helper used by all audit skills.
Provides GET and HEAD requests with consistent timeouts,
User-Agent headers, redirect handling, and graceful error handling.

Connection pooling: module-level singleton Session (TLS reuse across calls).
Rate limiting: per-host politeness delay (0.25s) to avoid 429s being
misread as WAF blocks. Lock guards only the timestamp dict, not the sleep.
"""
from __future__ import annotations

import sys
import time
import threading
import requests
import urllib3
from requests import Response
from typing import Optional
from urllib.parse import urlparse

# Suppress urllib3 SSL warnings when falling back to unverified requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Default timeout for all requests (connect, read)
DEFAULT_TIMEOUT = (5, 8)
DEFAULT_HEAD_TIMEOUT = (3, 4)

# Default User-Agent for general page fetching (non-bot-probe requests)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; BrandAIReadinessAudit/1.0; +https://github.com/Shubham00097/ai-website-audit)"
)

# --- Connection pooling: module-level singleton ---
_SESSION: Optional[requests.Session] = None
_SESSION_LOCK = threading.Lock()


def _session() -> requests.Session:
    """Return a module-level singleton requests.Session for connection reuse."""
    global _SESSION
    if _SESSION is None:
        with _SESSION_LOCK:
            if _SESSION is None:  # double-check under lock
                s = requests.Session()
                s.headers.update({"User-Agent": DEFAULT_USER_AGENT})
                _SESSION = s
    return _SESSION


# --- Per-host rate limiting (Correction 2) ---
# The lock only guards the dict read/write, NOT the sleep.
# This ensures a throttled call to host A does not block a concurrent call to host B.
MIN_INTERVAL = 0.25  # seconds between requests to the same host
_throttle_lock = threading.Lock()
_last_request_time: dict[str, float] = {}


def _throttle(host: str) -> None:
    """
    Enforce per-host politeness delay.
    Lock scope is minimised: only the dict lookup/update is inside the lock.
    The sleep (if any) happens OUTSIDE the lock so other hosts are not blocked.
    """
    with _throttle_lock:
        last = _last_request_time.get(host, 0)
        now = time.monotonic()
        wait = MIN_INTERVAL - (now - last)
        # Reserve our slot regardless of whether we need to sleep
        _last_request_time[host] = max(now, last + MIN_INTERVAL)
    if wait > 0:
        print(f"[throttle] {host}: sleeping {wait:.3f}s", file=sys.stderr)
        time.sleep(wait)


def get(
    url: str,
    user_agent: Optional[str] = None,
    timeout: tuple = DEFAULT_TIMEOUT,
    allow_redirects: bool = True,
    verify_ssl: bool = True,
) -> Optional[Response]:
    """
    Perform an HTTP GET request.

    Returns the Response object or None on failure.
    Never raises — errors are caught and returned as None.
    """
    host = urlparse(url).netloc
    _throttle(host)

    headers = {}
    if user_agent:
        headers["User-Agent"] = user_agent

    try:
        s = _session()
        response = s.get(
            url,
            headers=headers if headers else None,
            timeout=timeout,
            allow_redirects=allow_redirects,
            verify=verify_ssl,
        )
        return response
    except requests.exceptions.Timeout:
        return None
    except requests.exceptions.SSLError:
        # Retry without SSL verification
        try:
            return _session().get(
                url,
                headers=headers if headers else None,
                timeout=timeout,
                allow_redirects=allow_redirects,
                verify=False,
            )
        except Exception:
            return None
    except Exception:
        return None


def head(
    url: str,
    timeout: tuple = DEFAULT_HEAD_TIMEOUT,
    allow_redirects: bool = True,
    verify_ssl: bool = True,
) -> Optional[Response]:
    """
    Perform an HTTP HEAD request.

    Returns the Response object or None on failure.
    Falls back to GET if HEAD is rejected (405).
    Never raises.
    """
    host = urlparse(url).netloc
    _throttle(host)

    try:
        response = _session().head(
            url,
            timeout=timeout,
            allow_redirects=allow_redirects,
            verify=verify_ssl,
        )
        if response.status_code == 405:
            # Server does not support HEAD; fall back to GET
            return get(url, timeout=timeout, allow_redirects=allow_redirects)
        return response
    except Exception:
        return None


def status_code(url: str, user_agent: Optional[str] = None) -> Optional[int]:
    """Return only the HTTP status code for a URL, or None on failure."""
    resp = get(url, user_agent=user_agent)
    return resp.status_code if resp is not None else None
