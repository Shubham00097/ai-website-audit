"""
tests/test_dedup.py

Tests for the findings deduplication logic (shared/findings.py).
Key regression: two distinct findings with similar titles but different
evidence should NOT collapse into one.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shared.findings import Finding, deduplicate_findings, sort_findings, make_finding


def _make(title: str, severity: str, evidence: str = "Some evidence.", prefix: str = "TEST") -> Finding:
    return make_finding(
        skill_prefix=prefix,
        index=1,
        title=title,
        severity=severity,
        evidence=evidence,
        action_summary="Fix it.",
        action_priority=severity,
    )


def test_identical_findings_deduplicated():
    """Two identical findings (same title + evidence) collapse to one."""
    f1 = _make("No H1 found", "high", "No <h1> tag was found on the page.")
    f2 = _make("No H1 found", "high", "No <h1> tag was found on the page.")
    result = deduplicate_findings([f1, f2])
    assert len(result) == 1


def test_same_title_different_evidence_NOT_deduplicated():
    """
    Two findings with the same title but different evidence should remain distinct.
    Example: two schema types with the same 'missing required fields' title.
    """
    f1 = _make(
        "Schema missing required fields: author",
        "high",
        "Article schema at position 1 is missing: author, datePublished.",
    )
    f2 = _make(
        "Schema missing required fields: author",
        "high",
        "BlogPosting schema at position 2 is missing: author, publisher.",
    )
    result = deduplicate_findings([f1, f2])
    assert len(result) == 2, (
        "Two findings with same title but different evidence should NOT be collapsed"
    )


def test_higher_severity_wins_on_dedup():
    """When exact duplicates exist, the higher-severity one is kept."""
    f1 = _make("No H1 found", "medium", "No <h1> tag was found.")
    f2 = _make("No H1 found", "high", "No <h1> tag was found.")
    result = deduplicate_findings([f1, f2])
    assert len(result) == 1
    assert result[0].severity == "high"


def test_sort_findings_by_severity():
    """sort_findings() should order critical > high > medium > low."""
    findings = [
        _make("Low finding", "low", "Low evidence."),
        _make("Medium finding", "medium", "Medium evidence."),
        _make("Critical finding", "critical", "Critical evidence."),
        _make("High finding", "high", "High evidence."),
    ]
    sorted_f = sort_findings(findings)
    severities = [f.severity for f in sorted_f]
    assert severities == ["critical", "high", "medium", "low"]


def test_cross_skill_same_title_not_collapsed():
    """
    A finding titled 'No content found' from UX skill and the same title from
    CITE skill should coexist — they may have subtly different evidence.
    """
    f1 = _make("No content blocks found", "medium", "The engagement UX check found no paragraphs.", "UX")
    f2 = _make("No content blocks found", "medium", "The citability check found no text blocks.", "CITE")
    result = deduplicate_findings([f1, f2])
    assert len(result) == 2, "Cross-skill findings with different evidence must not collapse"
