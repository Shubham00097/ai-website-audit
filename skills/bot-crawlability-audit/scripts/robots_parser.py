"""
skills/bot-crawlability-audit/scripts/robots_parser.py

Parses robots.txt content and answers per-bot access questions.
Keeps robots parsing logic separate from HTTP probing logic.
"""
from __future__ import annotations

from typing import Optional
from urllib.robotparser import RobotFileParser
from shared.http_client import get


def fetch_robots_txt(base_url: str) -> Optional[str]:
    """Fetch raw robots.txt content. Returns None if unreachable."""
    url = base_url.rstrip("/") + "/robots.txt"
    resp = get(url)
    if resp is None or resp.status_code != 200:
        return None
    return resp.text


def parse_robots(robots_txt: str, base_url: str) -> RobotFileParser:
    """Parse robots.txt content into a RobotFileParser instance."""
    parser = RobotFileParser()
    parser.set_url(base_url.rstrip("/") + "/robots.txt")
    parser.parse(robots_txt.splitlines())
    return parser


def is_bot_allowed(parser: RobotFileParser, user_agent: str, path: str = "/") -> bool:
    """Return True if the given User-Agent is allowed to fetch the given path."""
    try:
        return parser.can_fetch(user_agent, path)
    except Exception:
        # On parse error, assume allowed (conservative)
        return True


def get_crawl_delay(parser: RobotFileParser, user_agent: str) -> Optional[float]:
    """Return the Crawl-delay directive for a given User-Agent, or None."""
    try:
        delay = parser.crawl_delay(user_agent)
        return float(delay) if delay is not None else None
    except Exception:
        return None
