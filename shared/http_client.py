"""
shared/http_client.py

Centralised HTTP helper used by all audit skills.
Provides GET and HEAD requests with consistent timeouts,
User-Agent headers, redirect handling, and graceful error handling.
"""
from __future__ import annotations

import requests
from requests import Response
from typing import Optional

# Default timeout for all requests (connect, read)
DEFAULT_TIMEOUT = (8, 15)

# Default User-Agent for general page fetching (non-bot-probe requests)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; BrandAIReadinessAudit/1.0; +https://github.com/Shubham00097/ai-website-audit)"
)


def _session() -> requests.Session:
    """Return a configured requests Session."""
    session = requests.Session()
    session.headers.update({"User-Agent": DEFAULT_USER_AGENT})
    return session


def get(
    url: str,
    user_agent: Optional[str] = None,
    timeout: tuple = DEFAULT_TIMEOUT,
    allow_redirects: bool = True,
    verify_ssl: bool = False,
) -> Optional[Response]:
    """
    Perform an HTTP GET request.

    Returns the Response object or None on failure.
    Never raises — errors are caught and returned as None.
    """
    headers = {}
    if user_agent:
        headers["User-Agent"] = user_agent

    try:
        session = _session()
        if headers:
            session.headers.update(headers)
        response = session.get(
            url,
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
            session = _session()
            if headers:
                session.headers.update(headers)
            return session.get(url, timeout=timeout, allow_redirects=allow_redirects, verify=False)
        except Exception:
            return None
    except Exception:
        return None


def head(
    url: str,
    timeout: tuple = DEFAULT_TIMEOUT,
    allow_redirects: bool = True,
    verify_ssl: bool = False,
) -> Optional[Response]:
    """
    Perform an HTTP HEAD request.

    Returns the Response object or None on failure.
    Falls back to GET if HEAD is rejected (405).
    Never raises.
    """
    try:
        session = _session()
        response = session.head(
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
