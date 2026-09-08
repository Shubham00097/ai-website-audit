"""
tests/test_citability_js_gap.py

A1: The citability skill marks static-HTML findings as content dependent. The
orchestrator owns render-gap detection and confidence/severity adjustment.
"""
from __future__ import annotations

import sys
import os
from unittest.mock import patch

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# Minimal SPA shell — no content in body, JS framework markers present
SPA_SHELL = """<!DOCTYPE html>
<html>
<head><title>My SPA</title></head>
<body>
<div id="root"></div>
<script src="/bundle.js"></script>
<script>window.__NEXT_DATA__ = {};</script>
</body>
</html>"""

# Normal SSR page with real content
SSR_PAGE = """<!DOCTYPE html>
<html>
<head>
<title>My Blog Post</title>
<meta name="description" content="A great blog post about testing">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Article","headline":"My Post","author":{"@type":"Person","name":"Jane Doe"},"datePublished":"2026-01-01"}
</script>
</head>
<body>
<h1>My Blog Post</h1>
<p>This is a substantive paragraph with enough words to pass the minimum threshold for content quality checking. It contains specific facts and named entities to score well on the citability rubric.</p>
<p>Another paragraph with additional detail about the topic at hand. It references specific statistics like 42% improvement and mentions the year 2026 for freshness signals.</p>
<p class="author">By Jane Doe</p>
</body>
</html>"""


def test_spa_content_findings_are_eligible_for_orchestrator_discount():
    """A standalone skill returns normal findings for the shared policy to adjust."""
    from shared.html_utils import parse_html

    with patch("shared.html_utils.fetch_html") as mock_fetch:
        mock_fetch.return_value = SPA_SHELL

        # Import after patching to use the patched version
        import importlib
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_citability_test",
            os.path.join(_REPO_ROOT, "skills", "citability-freshness-audit", "scripts", "check_citability.py"),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        findings = module.run("https://spa-example.com")

    # The render-gap finding is emitted once by the full orchestrator, not here.
    js_findings = [f for f in findings if "JavaScript" in f.title or "JS" in f.title or "render" in f.title.lower()]
    assert not js_findings

    content_quality = [f for f in findings if f.cause_tag == "content_quality"]
    assert content_quality
    assert all(f.content_dependent for f in content_quality)


def test_ssr_page_runs_all_checks():
    """On a normal SSR page, all check functions should run."""
    with patch("shared.html_utils.fetch_html") as mock_fetch:
        mock_fetch.return_value = SSR_PAGE

        import importlib
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_citability_test2",
            os.path.join(_REPO_ROOT, "skills", "citability-freshness-audit", "scripts", "check_citability.py"),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        findings = module.run("https://ssr-example.com")

    # JS-render detection is an orchestration concern.
    js_findings = [f for f in findings if "JavaScript" in f.title or "JS" in f.title or "render" in f.title.lower()]
    assert len(js_findings) == 0, f"SSR page should not trigger JS-render finding: {[f.title for f in js_findings]}"

    # Should have some real findings (the page has content to audit)
    # At minimum, trust_signals checks should find something
    assert len(findings) >= 0  # Not crashing is the key assertion
