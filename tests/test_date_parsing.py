"""
tests/test_date_parsing.py

Tests for the _parse_date() function in check_citability.py.
Verifies that ISO 8601 dates with timezone offsets (e.g., +05:30)
are correctly parsed — the original code's strptime truncation bug
would silently fail on these, causing false "no date" findings.
"""
import os
import sys
import importlib.util
import pytest
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load _parse_date from check_citability.py using importlib (hyphenated path)
_script_path = os.path.join(
    os.path.dirname(__file__), "..", "skills", "citability-freshness-audit",
    "scripts", "check_citability.py"
)
_spec = importlib.util.spec_from_file_location("check_citability", _script_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_parse_date = _mod._parse_date


@pytest.mark.parametrize("date_str,expected_year,expected_month,expected_day", [
    # ISO 8601 with UTC Z suffix (most common CMS output)
    ("2022-03-15T10:30:00Z", 2022, 3, 15),
    # ISO 8601 with positive TZ offset (India, etc.)
    ("2022-03-15T10:30:00+05:30", 2022, 3, 15),
    # ISO 8601 with negative TZ offset (US, etc.)
    ("2022-03-15T10:30:00-07:00", 2022, 3, 15),
    # ISO 8601 no timezone (naive — treated as UTC)
    ("2022-03-15T10:30:00", 2022, 3, 15),
    # Date-only format
    ("2022-03-15", 2022, 3, 15),
    # Older content
    ("2019-01-01T00:00:00Z", 2019, 1, 1),
])
def test_parse_date_valid_formats(date_str, expected_year, expected_month, expected_day):
    """All common date formats must be parsed correctly."""
    result = _parse_date(date_str)
    assert result is not None, f"Failed to parse date: '{date_str}'"
    assert result.year == expected_year
    assert result.month == expected_month
    assert result.day == expected_day
    # All results should be timezone-aware
    assert result.tzinfo is not None, f"Result for '{date_str}' is not timezone-aware"


def test_parse_date_returns_none_for_garbage():
    """Invalid date strings should return None, not raise an exception."""
    assert _parse_date("not-a-date") is None
    assert _parse_date("") is None
    assert _parse_date("undefined") is None
    assert _parse_date("null") is None


def test_stale_page_fires_high_finding():
    """
    A page with a 2022 datePublished should produce a 'stale content' finding.
    This is the end-to-end test: verify the soup mutation fix + date parsing fix
    together allow _check_freshness to actually run and detect staleness.
    """
    from bs4 import BeautifulSoup

    html = open(os.path.join(os.path.dirname(__file__), "fixtures", "stale_page.html")).read()
    soup = BeautifulSoup(html, "html.parser")

    findings = []
    idx = [1]
    _mod._check_freshness(soup, findings, idx)

    assert len(findings) >= 1, (
        "Expected at least 1 freshness finding for a 2022 page, got none. "
        "This likely indicates the date parsing or soup mutation bug is still present."
    )
    assert any(f.severity == "high" for f in findings), (
        "Expected a HIGH severity freshness finding for 3+ year old content."
    )


def test_fresh_page_does_not_fire():
    """A recently modified page should not trigger a staleness finding."""
    from bs4 import BeautifulSoup
    from datetime import datetime, timezone

    # Use current year to ensure it's always fresh
    current_year = datetime.now(timezone.utc).year
    html = f"""<html><head>
    <script type="application/ld+json">
    {{"@type": "Article", "dateModified": "{current_year}-01-01T00:00:00Z"}}
    </script></head><body><p>Fresh content.</p></body></html>"""

    soup = BeautifulSoup(html, "html.parser")
    findings = []
    _mod._check_freshness(soup, findings, [1])

    stale_findings = [f for f in findings if "stale" in f.title.lower()]
    assert len(stale_findings) == 0, (
        f"Fresh page should not trigger staleness, but got: {stale_findings}"
    )
