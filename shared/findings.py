"""
shared/findings.py

Standard Finding data structure and builder helpers used by all audit skills.
Centralises severity ordering and normalisation so the orchestrator
can sort/deduplicate without knowing skill internals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Dict, Any, Optional

Severity = Literal["critical", "high", "medium", "low"]
Priority = Literal["high", "medium", "low"]

RENDER_GAP_MANUAL_REVIEW = "manual review recommended — client-rendered page"

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
    snippet: Optional[str] = None  # B3: copy-pasteable fix snippet (e.g. JSON-LD template)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "summary": self.summary,
            "priority": self.priority,
        }
        if self.snippet is not None:
            d["snippet"] = self.snippet
        return d


@dataclass
class Finding:
    id: str
    title: str
    severity: Severity
    evidence: str
    suggested_action: SuggestedAction
    confidence: Optional[str] = None  # B4: e.g. "live HTTP probe", "static heuristic"
    cause_tag: Optional[str] = None   # Correction 4 / B1: root-cause grouping tag
    # Whether the result relies on static page HTML rather than an independent
    # HTTP/robots/header check. The orchestrator uses this to discount results
    # from pages whose meaningful content is rendered only in the browser.
    content_dependent: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "severity": self.severity,
            "evidence": self.evidence,
            "suggested_action": self.suggested_action.to_dict(),
        }
        if self.confidence is not None:
            d["confidence"] = self.confidence
        return d


def make_finding(
    skill_prefix: str,
    index: int,
    title: str,
    severity: Severity,
    evidence: str,
    action_summary: str,
    action_priority: Priority,
    confidence: Optional[str] = None,
    cause_tag: Optional[str] = None,
    snippet: Optional[str] = None,
    content_dependent: bool = False,
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
            snippet=snippet,
        ),
        confidence=confidence,
        cause_tag=cause_tag,
        content_dependent=content_dependent,
    )


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """
    Sort findings deterministically.

    Primary key: severity (critical first, low last).
    Tiebreakers (A3 fix): skill prefix from ID, then numeric index within skill.
    This ensures identical output regardless of ThreadPoolExecutor completion order.
    """
    def _sort_key(f: Finding) -> tuple:
        sev = SEVERITY_ORDER.get(f.severity, 99)
        # Extract skill prefix and index from IDs like "CRAWL-003" or "SCHEMA-001"
        parts = f.id.rsplit("-", 1)
        prefix = parts[0] if len(parts) == 2 else f.id
        try:
            idx = int(parts[1]) if len(parts) == 2 else 0
        except ValueError:
            idx = 0
        return (sev, prefix, idx)

    return sorted(findings, key=_sort_key)


def deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    """
    Remove duplicate findings based on (title, evidence-prefix) similarity.
    Preserves the highest-severity instance when duplicates exist.

    Uses a composite key of title + first 60 chars of evidence to distinguish
    findings that have similar titles but genuinely different evidence
    (e.g., two different schema types missing different required fields).
    """
    seen: Dict[str, Finding] = {}
    for f in findings:
        # Composite key: full normalised title + evidence prefix
        key = f"{f.title.lower().strip()}::{f.evidence[:60].lower().strip()}"
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
            confidence=f.confidence,
            cause_tag=f.cause_tag,
            content_dependent=f.content_dependent,
        ))
    return renumbered


def apply_render_gap_discount(findings: list[Finding], gap_info: Optional[dict]) -> list[Finding]:
    """Annotate content-dependent findings when static HTML is incomplete.

    A full client-rendering gap reduces the severity of static-HTML findings by
    one step. A partial gap preserves severity but still makes the uncertainty
    explicit. Findings based on robots.txt, live probes, and response headers
    remain untouched because they do not depend on rendered page content.
    """
    if not gap_info:
        return findings

    severity_after_full_gap = {
        "critical": "high",
        "high": "medium",
        "medium": "low",
        "low": "low",
    }
    is_partial = bool(gap_info.get("partial", False))

    for finding in findings:
        if not finding.content_dependent:
            continue
        finding.confidence = RENDER_GAP_MANUAL_REVIEW
        if not is_partial:
            finding.severity = severity_after_full_gap.get(finding.severity, finding.severity)

    return findings
