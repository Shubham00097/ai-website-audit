"""
tests/test_determinism.py

A3: Verify that sort_findings produces deterministic output regardless
of input ordering. Two different shuffles of the same findings must
produce byte-identical JSON after dedup → sort → renumber.
"""
from __future__ import annotations

import json
import random
import sys
import os

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.findings import (
    make_finding,
    sort_findings,
    deduplicate_findings,
    renumber_findings,
    Finding,
)


def _make_test_findings() -> list[Finding]:
    """Create a repeatable set of findings spanning multiple skills and severities."""
    return [
        make_finding("CRAWL", 1, "robots.txt missing", "high",
                      "No robots.txt found", "Add robots.txt", "high",
                      cause_tag="crawler_access", confidence="live HTTP probe"),
        make_finding("CRAWL", 2, "No llms.txt", "medium",
                      "No llms.txt found", "Add llms.txt", "medium",
                      cause_tag="crawler_access", confidence="live HTTP probe"),
        make_finding("SCHEMA", 1, "No structured data", "high",
                      "No JSON-LD found", "Add JSON-LD", "high",
                      cause_tag="entity_identity", confidence="static heuristic"),
        make_finding("SCHEMA", 2, "sameAs placeholder", "critical",
                      "sameAs: '#'", "Fix sameAs", "high",
                      cause_tag="entity_identity", confidence="static heuristic"),
        make_finding("CITE", 1, "Content stale", "high",
                      "Last modified 2 years ago", "Update content", "high",
                      cause_tag="content_freshness", confidence="static heuristic"),
        make_finding("CITE", 2, "No author", "medium",
                      "No author byline found", "Add author", "medium",
                      cause_tag="trust_signals", confidence="static heuristic"),
        make_finding("UX", 1, "No h1", "high",
                      "Page has no h1", "Add h1", "high",
                      cause_tag="onsite_orientation", confidence="static heuristic"),
        make_finding("UX", 2, "Meta description missing", "medium",
                      "No meta description", "Add meta", "medium",
                      cause_tag="onsite_orientation", confidence="static heuristic"),
        make_finding("UX", 3, "og:image missing", "low",
                      "No og:image", "Add og:image", "low",
                      cause_tag="onsite_orientation", confidence="static heuristic"),
    ]


def _pipeline(findings: list[Finding]) -> str:
    """Run the full dedup → sort → renumber pipeline and return JSON string."""
    result = deduplicate_findings(findings)
    result = sort_findings(result)
    result = renumber_findings(result)
    return json.dumps([f.to_dict() for f in result], indent=2, ensure_ascii=False)


def test_deterministic_ordering_across_shuffles():
    """Same input, two different shuffles → identical output."""
    findings_a = _make_test_findings()
    findings_b = _make_test_findings()

    # Shuffle A with a fixed seed
    random.seed(42)
    random.shuffle(findings_a)

    # Shuffle B with a different seed
    random.seed(999)
    random.shuffle(findings_b)

    # Ensure they're actually different orderings
    ids_a = [f.id for f in findings_a]
    ids_b = [f.id for f in findings_b]
    assert ids_a != ids_b, "Shuffles should produce different orderings"

    # Pipeline output must be identical
    output_a = _pipeline(findings_a)
    output_b = _pipeline(findings_b)
    assert output_a == output_b


def test_sort_order_is_severity_then_prefix_then_index():
    """Verify the exact sort order: severity → skill prefix → index."""
    findings = _make_test_findings()
    sorted_f = sort_findings(findings)
    ids = [f.id for f in sorted_f]

    # Expected: critical first, then highs (CITE < CRAWL < SCHEMA < UX),
    # then mediums, then lows
    assert ids[0] == "SCHEMA-002"  # critical
    # Highs: CITE-001, CRAWL-001, SCHEMA-001, UX-001
    high_ids = [f.id for f in sorted_f if f.severity == "high"]
    assert high_ids == ["CITE-001", "CRAWL-001", "SCHEMA-001", "UX-001"]
    # Mediums: CITE-002, CRAWL-002, UX-002
    medium_ids = [f.id for f in sorted_f if f.severity == "medium"]
    assert medium_ids == ["CITE-002", "CRAWL-002", "UX-002"]
    # Low: UX-003
    low_ids = [f.id for f in sorted_f if f.severity == "low"]
    assert low_ids == ["UX-003"]


def test_renumbered_ids_are_sequential():
    """After renumbering, IDs must be F-001, F-002, ... with no gaps."""
    findings = _make_test_findings()
    result = sort_findings(findings)
    result = renumber_findings(result)
    expected_ids = [f"F-{i:03d}" for i in range(1, len(result) + 1)]
    actual_ids = [f.id for f in result]
    assert actual_ids == expected_ids
