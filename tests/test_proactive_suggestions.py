"""End-to-end coverage for defect-independent report suggestions."""
from __future__ import annotations

import importlib.util
import os
import sys
from unittest.mock import patch


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _load_orchestrator():
    path = os.path.join(
        _REPO_ROOT, "skills", "audit-orchestrator", "scripts", "orchestrator.py"
    )
    spec = importlib.util.spec_from_file_location("orchestrator_proactive_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code
        self.headers = {"Content-Type": "text/html"}


def test_valid_jsonld_page_still_gets_non_duplicate_proactive_suggestion():
    """Suggestions remain available even when schema validation finds no defect."""
    fixture_path = os.path.join(_REPO_ROOT, "tests", "fixtures", "rich_page.html")
    with open(fixture_path, encoding="utf-8") as f:
        rich_page = f.read()

    def fake_get(url, *args, **kwargs):
        if url.endswith("/robots.txt"):
            return _Response("User-agent: *\nAllow: /\n")
        if "linkedin.com" in url:
            return _Response("<html><body><h1>Acme Corp</h1></body></html>")
        return _Response(rich_page)

    def fake_head(url, *args, **kwargs):
        return _Response()

    orchestrator = _load_orchestrator()
    with patch("shared.http_client.get", side_effect=fake_get), \
         patch("shared.http_client.head", side_effect=fake_head), \
         patch("shared.html_utils.get", side_effect=fake_get):
        report = orchestrator.audit("https://acme.example")

    assert report["proactive_suggestions"]
    titles = [suggestion["title"] for suggestion in report["proactive_suggestions"]]
    assert "Add FAQPage schema for answer-led AI queries" in titles
    assert all("severity" not in suggestion for suggestion in report["proactive_suggestions"])
    assert not any("No structured data found" in finding["title"] for finding in report["findings"])
