"""
shared/url_utils.py

URL normalisation and validation helpers used by all skills.
"""
from __future__ import annotations

from urllib.parse import urlparse, urljoin
from typing import Optional


def normalise_url(url: str) -> str:
    """
    Ensure a URL has a scheme.
    Prepends https:// if no scheme is present.
    """
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def validate_url(url: str) -> bool:
    """Return True if the URL has a valid scheme and netloc."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def base_url(url: str) -> str:
    """
    Return the scheme + netloc of a URL.
    Example: https://example.com/path → https://example.com
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def get_domain(url: str) -> str:
    """Extract the domain (netloc) from a URL."""
    return urlparse(url).netloc


def resolve(base: str, path: str) -> str:
    """
    Resolve a relative path against a base URL.
    Example: resolve('https://example.com', '/robots.txt') → 'https://example.com/robots.txt'
    """
    return urljoin(base, path)


def robots_url(url: str) -> str:
    """Return the robots.txt URL for a given site URL."""
    return resolve(base_url(url), "/robots.txt")


def sitemap_url(url: str) -> str:
    """Return the sitemap.xml URL for a given site URL."""
    return resolve(base_url(url), "/sitemap.xml")


def llms_txt_url(url: str) -> str:
    """Return the /llms.txt URL for a given site URL."""
    return resolve(base_url(url), "/llms.txt")


def llms_full_txt_url(url: str) -> str:
    """Return the /llms-full.txt URL for a given site URL."""
    return resolve(base_url(url), "/llms-full.txt")
