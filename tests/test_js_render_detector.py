"""
tests/test_js_render_detector.py

Tests for the JS render gap detection module (shared/js_render_detector.py).
Covers: SPA detection, SSR pass-through, partial SSR, frameworkless detection.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bs4 import BeautifulSoup
from shared.js_render_detector import detect_js_render_gap, emit_js_render_finding
from shared.findings import Finding


def _parse(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# --- Fixtures ---

SPA_NEXTJS = open(os.path.join(os.path.dirname(__file__), "fixtures", "spa_shell.html")).read()
RICH_PAGE = open(os.path.join(os.path.dirname(__file__), "fixtures", "rich_page.html")).read()


def test_nextjs_spa_detected():
    """Next.js SPA with empty body should be detected as a render gap."""
    soup = _parse(SPA_NEXTJS)
    result = detect_js_render_gap(SPA_NEXTJS, soup)
    assert result is not None, "Next.js SPA should be detected as a JS render gap"
    assert result["framework"] == "Next.js"
    assert result.get("partial", False) is False
    assert result["body_text_words"] < 80


def test_rich_ssr_page_not_flagged():
    """A well-structured SSR page should NOT be flagged as a JS render gap."""
    soup = _parse(RICH_PAGE)
    result = detect_js_render_gap(RICH_PAGE, soup)
    assert result is None, (
        f"SSR page should not be flagged as a render gap, but got: {result}"
    )


def test_react_spa_detected():
    """React SPA with data-reactroot marker should be detected."""
    html = """<html><head></head><body>
    <div data-reactroot=""></div>
    <script src="/static/js/main.chunk.js"></script>
    <script src="/static/js/vendor.chunk.js"></script>
    <script src="/static/js/runtime.chunk.js"></script>
    <script src="/static/js/app.chunk.js"></script>
    <script src="/static/js/utils.chunk.js"></script>
    </body></html>"""
    soup = _parse(html)
    result = detect_js_render_gap(html, soup)
    assert result is not None, "React SPA should be detected"
    assert result["framework"] == "React"


def test_angular_detected():
    """Angular app should be detected via ng-version attribute."""
    html = """<html><head></head><body>
    <app-root ng-version="15.2.0"></app-root>
    <script src="/main.js"></script>
    <script src="/polyfills.js"></script>
    <script src="/vendor.js"></script>
    <script src="/runtime.js"></script>
    </body></html>"""
    soup = _parse(html)
    result = detect_js_render_gap(html, soup)
    assert result is not None, "Angular app should be detected"
    assert result["framework"] == "Angular"


def test_no_framework_empty_body_detected():
    """A frameworkless SPA with empty body and many scripts should be detected."""
    html = """<html><head></head><body>
    <div id="app"></div>
    <script src="/bundle1.js"></script>
    <script src="/bundle2.js"></script>
    <script src="/bundle3.js"></script>
    <script src="/bundle4.js"></script>
    <script src="/bundle5.js"></script>
    </body></html>"""
    soup = _parse(html)
    result = detect_js_render_gap(html, soup)
    assert result is not None, "Frameworkless empty SPA should still be detected"
    assert result["framework"] is None


def test_emit_creates_finding():
    """emit_js_render_finding() should append a Finding to the list."""
    gap_info = {
        "framework": "Next.js",
        "body_text_words": 5,
        "script_count": 4,
        "partial": False,
        "evidence": "Test evidence",
    }
    findings: list[Finding] = []
    idx = [1]
    emit_js_render_finding(gap_info, "UX", findings, idx)

    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "high"
    assert "JavaScript rendering" in f.title or "JS render" in f.title.lower() or "rendering" in f.title.lower()
    assert idx[0] == 2  # Index incremented


def test_partial_ssr_severity_is_medium():
    """Partial SSR should emit a medium-severity finding, not high."""
    gap_info = {
        "framework": "Vue 3",
        "body_text_words": 150,
        "script_count": 5,
        "partial": True,
        "evidence": "Partial SSR detected",
    }
    findings: list[Finding] = []
    emit_js_render_finding(gap_info, "UX", findings, [1])
    assert findings[0].severity == "medium"
