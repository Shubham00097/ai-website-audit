"""
shared/findings.py

Standard Finding data structure and builder helpers used by all audit skills.
Centralises severity ordering and normalisation so the orchestrator
can sort/deduplicate without knowing skill internals.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal, Dict, Any

Severity = Literal["critical", "high", "medium", "low"]
Priority = Literal["high", "medium", "low"]

SEVERITY_ORDER: Dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


@dataclass
class SuggestedAction:
    summary: str
    priority: Priority


@dataclass
class Finding:
    id: str
    title: str
    severity: Severity
    evidence: str
    suggested_action: SuggestedAction

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "severity": self.severity,
            "evidence": self.evidence,
            "suggested_action": {
                "summary": self.suggested_action.summary,
                "priority": self.suggested_action.priority,
            },
        }


def make_finding(
    skill_prefix: str,
    index: int,
    title: str,
    severity: Severity,
    evidence: str,
    action_summary: str,
    action_priority: Priority,
) -> Finding:
    """
    Construct a Finding with a deterministic ID.

    ID format: <SKILL_PREFIX>-<zero-padded-index>
    Example:   CRAWL-001, SCHEMA-003
    """
    finding_id = f"{skill_prefix}-{index:03d}"
    return Finding(
        id=finding_id,
        title=title,
        severity=severity,
        evidence=evidence,
        suggested_action=SuggestedAction(
            summary=action_summary,
            priority=action_priority,
        ),
    )


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Sort findings by severity (critical first, low last)."""
    return sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 99))


def deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    """
    Remove duplicate findings based on title similarity.
    Preserves the highest-severity instance when duplicates exist.
    """
    seen: Dict[str, Finding] = {}
    for f in findings:
        key = f.title.lower().strip()
        if key not in seen:
            seen[key] = f
        else:
            # Keep the one with higher severity
            existing = seen[key]
            if SEVERITY_ORDER.get(f.severity, 99) < SEVERITY_ORDER.get(existing.severity, 99):
                seen[key] = f
    return list(seen.values())


def renumber_findings(findings: list[Finding]) -> list[Finding]:
    """Re-assign sequential F-001, F-002, ... IDs after merging all skills."""
    renumbered = []
    for i, f in enumerate(findings, start=1):
        renumbered.append(Finding(
            id=f"F-{i:03d}",
            title=f.title,
            severity=f.severity,
            evidence=f.evidence,
            suggested_action=f.suggested_action,
        ))
    return renumbered
