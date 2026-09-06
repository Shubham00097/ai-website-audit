"""
tests/test_orchestrator_partial_failure.py

A5: Verify that if one sub-skill crashes, the orchestrator:
  - Still returns a valid report
  - Lists the crashing skill in skills_failed
  - Includes findings from other skills
  - Produces sequential F-IDs
  - Report validates against audit_schema.json
"""
from __future__ import annotations

import json
import os
import sys
import importlib
import importlib.util
from unittest.mock import patch, MagicMock

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.findings import make_finding, Finding


def _load_orchestrator():
    """Import the orchestrator module from its non-standard path."""
    script_path = os.path.join(_REPO_ROOT, "skills", "audit-orchestrator", "scripts", "orchestrator.py")
    spec = importlib.util.spec_from_file_location("orchestrator_module", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mock_skill_results(url):
    """
    Simulate: 
      - bot-crawlability-audit returns 2 findings
      - structured-data-audit raises RuntimeError
      - citability-freshness-audit returns 1 finding
      - engagement-ux-audit returns 1 finding
    """
    return {
        "bot-crawlability-audit": [
            make_finding("CRAWL", 1, "robots.txt missing", "high",
                         "No robots.txt", "Add robots.txt", "high",
                         confidence="live HTTP probe", cause_tag="crawler_access"),
            make_finding("CRAWL", 2, "No llms.txt", "medium",
                         "No llms.txt found", "Add llms.txt", "medium",
                         confidence="live HTTP probe", cause_tag="crawler_access"),
        ],
        "structured-data-audit": RuntimeError("Simulated crash"),
        "citability-freshness-audit": [
            make_finding("CITE", 1, "Content stale", "high",
                         "Last modified 2 years ago", "Update content", "high",
                         confidence="static heuristic", cause_tag="content_freshness"),
        ],
        "engagement-ux-audit": [
            make_finding("UX", 1, "No h1", "high",
                         "Page has no h1 tag", "Add h1", "high",
                         confidence="static heuristic", cause_tag="onsite_orientation"),
        ],
    }


@pytest.fixture
def orchestrator_module():
    return _load_orchestrator()


def test_partial_failure_report_structure(orchestrator_module):
    """Crashing sub-skill should not prevent report generation."""
    mock_results = _mock_skill_results("https://example.com")

    def mock_run_skill(name, run_fn, url):
        result = mock_results.get(name)
        if isinstance(result, Exception):
            return name, [], str(result)
        return name, result, None

    def mock_import_skills():
        return {
            "bot-crawlability-audit": lambda url: mock_results["bot-crawlability-audit"],
            "structured-data-audit": lambda url: (_ for _ in ()).throw(mock_results["structured-data-audit"]),
            "citability-freshness-audit": lambda url: mock_results["citability-freshness-audit"],
            "engagement-ux-audit": lambda url: mock_results["engagement-ux-audit"],
        }

    with patch.object(orchestrator_module, "_import_skills", mock_import_skills), \
         patch.object(orchestrator_module, "_run_skill", side_effect=mock_run_skill):
        report = orchestrator_module.audit("https://example.com")

    # Basic structure
    assert "site" in report
    assert "audited_at" in report
    assert "summary" in report
    assert "findings" in report
    assert "metadata" in report

    # Failed skill listed
    assert "structured-data-audit" in report["metadata"]["skills_failed"]

    # Other skills' findings present
    assert report["summary"]["total_findings"] == 4

    # F-IDs are sequential
    ids = [f["id"] for f in report["findings"]]
    assert ids == ["F-001", "F-002", "F-003", "F-004"]

    # Headline present (B2)
    assert "headline" in report["summary"]
    assert len(report["summary"]["headline"]) > 0

    # Root causes present (B1)
    assert "root_causes" in report
    assert len(report["root_causes"]) > 0


def test_report_validates_against_schema(orchestrator_module):
    """Report should validate against audit_schema.json."""
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema_path = os.path.join(
        _REPO_ROOT, "skills", "audit-orchestrator", "references", "audit_schema.json"
    )
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    mock_results = _mock_skill_results("https://example.com")

    def mock_run_skill(name, run_fn, url):
        result = mock_results.get(name)
        if isinstance(result, Exception):
            return name, [], str(result)
        return name, result, None

    def mock_import_skills():
        return {
            "bot-crawlability-audit": lambda url: mock_results["bot-crawlability-audit"],
            "structured-data-audit": lambda url: (_ for _ in ()).throw(mock_results["structured-data-audit"]),
            "citability-freshness-audit": lambda url: mock_results["citability-freshness-audit"],
            "engagement-ux-audit": lambda url: mock_results["engagement-ux-audit"],
        }

    with patch.object(orchestrator_module, "_import_skills", mock_import_skills), \
         patch.object(orchestrator_module, "_run_skill", side_effect=mock_run_skill):
        report = orchestrator_module.audit("https://example.com")

    # The schema only validates the base required fields, additional fields are OK
    jsonschema.validate(instance=report, schema=schema)
