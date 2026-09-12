"""End-to-end regression coverage for the uniform render-gap policy."""
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
    spec = importlib.util.spec_from_file_location("orchestrator_render_gap_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code
        self.headers = {"Content-Type": "text/html"}


def test_full_render_gap_discounts_ux_findings_and_clusters_render_cause():
    """The complete audit discounts static UX results but preserves the signal."""
    spa_html = """<!doctype html><html><head>
    <script id=\"__NEXT_DATA__\" type=\"application/json\">{}</script>
    </head><body><div id=\"__next\">Hello</div>
    <script src=\"/one.js\"></script><script src=\"/two.js\"></script>
    <script src=\"/three.js\"></script><script src=\"/four.js\"></script>
    </body></html>"""

    def fake_get(url, *args, **kwargs):
        if url.endswith("/robots.txt"):
            return _Response("User-agent: *\nAllow: /\n")
        return _Response(spa_html)

    def fake_head(url, *args, **kwargs):
        return _Response()

    orchestrator = _load_orchestrator()
    with patch("shared.http_client.get", side_effect=fake_get), \
         patch("shared.http_client.head", side_effect=fake_head), \
         patch("shared.html_utils.get", side_effect=fake_get):
        report = orchestrator.audit("https://spa.example.test")

    by_title = {finding["title"]: finding for finding in report["findings"]}
    for title in (
        "No <h1> heading found on the page",
        "No clear Call to Action (CTA) detected on the page",
        "No navigation element found",
    ):
        finding = by_title[title]
        assert finding["severity"] == "medium"
        assert finding["confidence"] == "manual review recommended — client-rendered page"

    render_cluster = next(
        cluster for cluster in report["root_causes"]
        if cluster["cause"] == "javascript_rendering"
    )
    assert render_cluster["label"] == "JavaScript Rendering"
    assert all(cluster["cause"] != "uncategorised" for cluster in report["root_causes"])
