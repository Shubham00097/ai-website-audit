"""
shared/html_utils.py

HTML fetching and parsing helpers shared across all audit skills.
Wraps BeautifulSoup so individual skills do not import it directly.
"""
from __future__ import annotations

from typing import Optional
from bs4 import BeautifulSoup
from shared.http_client import get


def fetch_html(url: str) -> Optional[str]:
    """
    Fetch the raw HTML of a URL.
    Returns the response text or None on failure.
    """
    response = get(url)
    if response is None:
        return None
    # Only accept HTML-like content types
    content_type = response.headers.get("Content-Type", "")
    if response.status_code != 200:
        return None
    return response.text


def parse_html(html: str) -> BeautifulSoup:
    """Parse an HTML string into a BeautifulSoup object."""
    return BeautifulSoup(html, "html.parser")


def fetch_and_parse(url: str) -> Optional[BeautifulSoup]:
    """
    Fetch a URL and return a parsed BeautifulSoup object.
    Returns None if the fetch fails or content is not HTML.
    """
    html = fetch_html(url)
    if html is None:
        return None
    return parse_html(html)


def get_meta_content(soup: BeautifulSoup, name: str) -> Optional[str]:
    """
    Extract content from a <meta name="..."> tag.
    Case-insensitive name matching.
    """
    tag = soup.find("meta", attrs={"name": lambda v: v and v.lower() == name.lower()})
    if tag:
        return tag.get("content", "").strip() or None
    return None


def get_og_property(soup: BeautifulSoup, prop: str) -> Optional[str]:
    """Extract content from a <meta property="og:..."> tag."""
    tag = soup.find("meta", attrs={"property": prop})
    if tag:
        return tag.get("content", "").strip() or None
    return None


def get_all_text_blocks(soup: BeautifulSoup, min_words: int = 20) -> list[str]:
    """
    Extract all paragraph text blocks with at least min_words words.
    Strips script/style content.
    """
    # Remove script and style tags
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    blocks = []
    for p in soup.find_all("p"):
        text = p.get_text(separator=" ", strip=True)
        if len(text.split()) >= min_words:
            blocks.append(text)
    return blocks
