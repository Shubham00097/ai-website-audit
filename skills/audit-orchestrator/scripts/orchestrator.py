"""
skills/audit-orchestrator/scripts/orchestrator.py

Entry point for the Brand AI Readiness Audit.

Usage:
    python orchestrator.py <url>
    python orchestrator.py https://example.com
    python orchestrator.py https://example.com --output report.json
    python orchestrator.py https://example.com --pretty

Runs all 4 audit sub-skills in parallel, aggregates findings,
deduplicates, sorts by severity, and emits the required JSON report.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

# Fix Windows terminal encoding for Unicode characters
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

# Ensure repo root is in path regardless of working directory
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.url_utils import normalise_url, validate_url, get_domain
from shared.findings import Finding, sort_findings, deduplicate_findings, renumber_findings

# Import sub-skill run() functions
# Each returns list[Finding] or raises an exception on critical failure
def _import_skills():
    """
    Import sub-skills using importlib to handle hyphenated directory names.
    Returns a dict of {skill_name: run_function_or_None}.
    """
    import importlib.util

    skill_configs = [
        ("bot-crawlability-audit",     "check_crawlers.py"),
        ("structured-data-audit",      "check_schema.py"),
        ("citability-freshness-audit", "check_citability.py"),
        ("engagement-ux-audit",        "check_engagement.py"),
    ]

    skills = {}
    for skill_name, script_file in skill_configs:
        script_path = os.path.join(
            _REPO_ROOT, "skills", skill_name, "scripts", script_file
        )
        if not os.path.isfile(script_path):
            skills[skill_name] = None
            print(f"[WARN] Script not found: {script_path}", file=sys.stderr)
            continue
        try:
            module_name = skill_name.replace("-", "_") + "_run"
            spec = importlib.util.spec_from_file_location(module_name, script_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            skills[skill_name] = module.run
        except Exception as e:
            skills[skill_name] = None
            print(f"[WARN] Could not load {skill_name}: {e}", file=sys.stderr)

    return skills


def _run_skill(name: str, run_fn, url: str) -> tuple[str, list[Finding], Optional[str]]:
    """
    Execute a single skill's run() function.
    Returns (name, findings, error_message_or_None).
    Never raises — errors are captured and returned.
    """
    try:
        findings = run_fn(url)
        return name, findings or [], None
    except Exception as exc:
        return name, [], str(exc)


def _build_report(
    url: str,
    findings: list[Finding],
    skills_run: list[str],
    skills_failed: list[str],
    duration: float,
) -> dict:
    """Assemble the final JSON report dict."""
    domain = get_domain(url) or url
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        if f.severity in severity_counts:
            severity_counts[f.severity] += 1

    return {
        "site": domain,
        "audited_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {
            "total_findings": len(findings),
            **severity_counts,
        },
        "findings": [f.to_dict() for f in findings],
        "metadata": {
            "skills_run": skills_run,
            "skills_failed": skills_failed,
            "duration_seconds": round(duration, 2),
        },
    }


def audit(url: str) -> dict:
    """
    Run the full Brand AI Readiness Audit.

    Args:
        url: The website URL to audit.

    Returns:
        The final audit report as a dict.
    """
    url = normalise_url(url)
    if not validate_url(url):
        print(f"[ERROR] Invalid URL: {url}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Starting Brand AI Readiness Audit for: {url}", file=sys.stderr)
    start_time = time.time()

    skills = _import_skills()
    all_findings: list[Finding] = []
    skills_run: list[str] = []
    skills_failed: list[str] = []

    # Run available skills in parallel (max 4 workers — one per skill)
    available = {name: fn for name, fn in skills.items() if fn is not None}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_run_skill, name, fn, url): name
            for name, fn in available.items()
        }
        for future in as_completed(futures):
            skill_name = futures[future]
            name, findings, error = future.result()
            if error:
                print(f"[WARN] {name} failed: {error}", file=sys.stderr)
                skills_failed.append(name)
            else:
                print(f"[+] {name}: {len(findings)} finding(s)", file=sys.stderr)
                skills_run.append(name)
                all_findings.extend(findings)

    # Skills that couldn't be imported
    for name, fn in skills.items():
        if fn is None:
            skills_failed.append(name)

    # Aggregate: deduplicate → sort by severity → renumber
    all_findings = deduplicate_findings(all_findings)
    all_findings = sort_findings(all_findings)
    all_findings = renumber_findings(all_findings)

    duration = time.time() - start_time
    print(f"[*] Audit complete in {duration:.1f}s — {len(all_findings)} total finding(s)", file=sys.stderr)

    return _build_report(url, all_findings, skills_run, skills_failed, duration)


def main():
    parser = argparse.ArgumentParser(
        description="Brand AI Readiness Audit — Agent Skill Marketplace",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python orchestrator.py https://example.com\n"
            "  python orchestrator.py https://example.com --output report.json\n"
            "  python orchestrator.py https://example.com --pretty\n"
        ),
    )
    parser.add_argument("url", help="Website URL to audit")
    parser.add_argument(
        "--output", "-o",
        default="audit_report.json",
        help="Output file path (default: audit_report.json)",
    )
    parser.add_argument(
        "--pretty", action="store_true",
        help="Pretty-print JSON with indentation",
    )
    parser.add_argument(
        "--stdout-only", action="store_true",
        help="Print to stdout only, do not save a file",
    )
    args = parser.parse_args()

    report = audit(args.url)
    indent = 2 if args.pretty else None
    report_json = json.dumps(report, indent=indent, ensure_ascii=False)

    # Print to stdout
    print(report_json)

    # Save to file unless --stdout-only
    if not args.stdout_only:
        output_path = os.path.abspath(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\n[*] Report saved to: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
