"""
tests/test_html_utils.py

Tests that get_all_text_blocks() does NOT mutate the shared soup object.
This is the fix for A14: the original code called tag.decompose() which
permanently removed <script> tags from the soup, breaking subsequent
calls to _check_freshness() that needed those same <script> tags.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bs4 import BeautifulSoup
from shared.html_utils import get_all_text_blocks, parse_html


# Fixture: page with both <p> content and <script type="application/ld+json">
SAMPLE_HTML = """
<html>
<head>
  <script type="application/ld+json">{"@type": "Article", "datePublished": "2025-01-01"}</script>
</head>
<body>
  <p>The Widget Pro is our flagship industrial component with ISO 9001 certification.</p>
  <p>According to our 2025 annual report, we processed 12.4 million units with a defect rate below 0.003 percent.</p>
  <script>var x = 1;</script>
  <noscript><p>Please enable JavaScript.</p></noscript>
</body>
</html>
"""


def test_get_all_text_blocks_does_not_mutate_soup():
    """
    After calling get_all_text_blocks(), <script type="application/ld+json">
    tags must still be present and parseable in the soup.
    """
    soup = parse_html(SAMPLE_HTML)

    # Verify scripts exist before the call
    json_ld_before = soup.find_all("script", type="application/ld+json")
    assert len(json_ld_before) == 1, "Expected 1 JSON-LD script tag before call"

    # Call the function
    blocks = get_all_text_blocks(soup, min_words=5)

    # Verify scripts still exist after the call
    json_ld_after = soup.find_all("script", type="application/ld+json")
    assert len(json_ld_after) == 1, (
        "get_all_text_blocks() mutated the soup and removed <script type='application/ld+json'> tags! "
        "This breaks _check_freshness() which scans for JSON-LD dates after this call."
    )


def test_get_all_text_blocks_returns_correct_paragraphs():
    """Verify the function returns paragraphs with >= min_words words."""
    soup = parse_html(SAMPLE_HTML)
    blocks = get_all_text_blocks(soup, min_words=5)
    assert len(blocks) >= 2, "Expected at least 2 paragraph blocks"
    for block in blocks:
        assert len(block.split()) >= 5


def test_get_all_text_blocks_excludes_noscript_content():
    """
    Text inside <noscript> should not appear in content blocks
    (it's not what the AI crawler sees in normal operation).
    """
    html = """
    <html><body>
    <noscript><p>Please enable JavaScript to view this page content.</p></noscript>
    <p>Normal content that AI crawlers can always see regardless of JavaScript support.</p>
    </body></html>
    """
    soup = parse_html(html)
    blocks = get_all_text_blocks(soup, min_words=5)
    # Should not include the noscript content as a standalone block
    noscript_text = "Please enable JavaScript"
    for block in blocks:
        assert noscript_text not in block, (
            f"noscript content leaked into text blocks: {block}"
        )


def test_get_all_text_blocks_min_words_filter():
    """Short paragraphs below min_words threshold are excluded."""
    html = """<html><body>
    <p>Short.</p>
    <p>This paragraph contains more than twenty words because it has been deliberately extended with additional words to surpass the minimum threshold for inclusion in the content blocks list.</p>
    </body></html>"""
    soup = parse_html(html)
    blocks = get_all_text_blocks(soup, min_words=20)
    assert len(blocks) == 1
    assert "minimum threshold" in blocks[0]
