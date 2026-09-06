"""
tests/test_schema_js_gap.py

Correction 3: Verify check_schema.py handles JS-render gaps correctly.
On a SPA shell with no static JSON-LD, it should:
  - Report "No structured data found" (not crash)
  - Mark confidence as "manual review recommended" (not "static heuristic")
  - Include the JS-gap annotation in evidence
This proves the failure mode is an accepted false negative, not something worse.
"""
from __future__ import annotations

import sys
import os
from unittest.mock import patch

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# SPA shell: GTM-style page that would inject JSON-LD at runtime.
# No static <script type="application/ld+json"> — structured data
# would only appear after JavaScript execution.
GTM_SPA_SHELL = """<!DOCTYPE html>
<html>
<head>
<title>GTM-Injected Schema</title>
<!-- Google Tag Manager would inject JSON-LD here at runtime -->
<script>
  window.dataLayer = window.dataLayer || [];
  // GTM would create and inject <script type="application/ld+json"> dynamically
</script>
</head>
<body>
<div id="root"></div>
<script src="/app-bundle.js"></script>
<script>window.__NEXT_DATA__ = {"page":"/","query":{}};</script>
</body>
</html>"""


def _load_schema_module():
    """Import check_schema from its non-standard path."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "check_schema_test",
        os.path.join(_REPO_ROOT, "skills", "structured-data-audit", "scripts", "check_schema.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gtm_spa_reports_no_structured_data():
    """On a GTM-style SPA with no static JSON-LD, report 'no structured data' — don't crash."""
    with patch("shared.html_utils.fetch_html") as mock_fetch:
        mock_fetch.return_value = GTM_SPA_SHELL
        module = _load_schema_module()
        findings = module.run("https://gtm-spa.example.com")

    # Should find at least one finding about missing structured data
    assert len(findings) >= 1
    titles = [f.title for f in findings]
    assert any("No structured data" in t or "no structured data" in t.lower() for t in titles), \
        f"Expected 'No structured data' finding, got: {titles}"


def test_gtm_spa_has_reduced_confidence():
    """On a JS-render-gap page, confidence should be 'manual review recommended'."""
    with patch("shared.html_utils.fetch_html") as mock_fetch:
        mock_fetch.return_value = GTM_SPA_SHELL
        module = _load_schema_module()
        findings = module.run("https://gtm-spa.example.com")

    # The "no structured data" finding should have reduced confidence
    no_data_finding = None
    for f in findings:
        if "structured data" in f.title.lower():
            no_data_finding = f
            break

    assert no_data_finding is not None
    assert no_data_finding.confidence == "manual review recommended", \
        f"Expected 'manual review recommended', got: {no_data_finding.confidence}"


def test_gtm_spa_evidence_mentions_js_render():
    """Evidence should mention client-side rendering for transparency."""
    with patch("shared.html_utils.fetch_html") as mock_fetch:
        mock_fetch.return_value = GTM_SPA_SHELL
        module = _load_schema_module()
        findings = module.run("https://gtm-spa.example.com")

    no_data_finding = None
    for f in findings:
        if "structured data" in f.title.lower():
            no_data_finding = f
            break

    assert no_data_finding is not None
    assert "client-side rendering" in no_data_finding.evidence.lower(), \
        f"Evidence should mention client-side rendering: {no_data_finding.evidence[:200]}"
