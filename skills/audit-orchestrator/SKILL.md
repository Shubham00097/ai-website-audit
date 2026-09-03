---
name: audit-orchestrator
version: "1.0.0"
description: >
  Entrypoint skill that composes all Brand AI Readiness Audit sub-skills,
  aggregates findings, and emits a structured JSON report.
role: entrypoint
parameters:
  - name: url
    type: string
    required: true
    description: The website URL to audit (e.g. https://example.com)
  - name: output_file
    type: string
    required: false
    description: Optional path to save the JSON report (default: audit_report.json)
allowed_tools:
  - read_file
  - execute_python
---

# Audit Orchestrator

## Purpose

This is the **entrypoint** for the Brand AI Readiness Audit marketplace.
It accepts a target URL, runs four specialised audit skills in parallel, and
produces a single structured JSON report conforming to the required output schema.

## How to Run

```bash
python skills/audit-orchestrator/scripts/orchestrator.py <url>
python skills/audit-orchestrator/scripts/orchestrator.py https://example.com
python skills/audit-orchestrator/scripts/orchestrator.py https://example.com --output my_report.json
```

## What It Does

1. Validates and normalises the input URL.
2. Runs all four sub-skills concurrently using Python ThreadPoolExecutor.
3. Collects findings from each sub-skill.
4. Merges and deduplicates findings across skills.
5. Sorts findings by severity (critical → high → medium → low).
6. Re-numbers findings as F-001, F-002, …
7. Generates a summary (total and count per severity level).
8. Emits a JSON report to stdout and saves to `audit_report.json`.

## Sub-Skills Composed

| Skill | Responsibility |
|---|---|
| `bot-crawlability-audit` | AI crawler access, robots.txt, llms.txt, WAF detection |
| `structured-data-audit` | JSON-LD, schema.org, entity disambiguation |
| `citability-freshness-audit` | Content extractability, freshness, cloaking |
| `engagement-ux-audit` | Headings, readability, CTA, Open Graph |

## Output Schema

See `references/audit_schema.json` for the full JSON Schema definition.
See `references/severity_matrix.md` for severity assignment rules.

## Failure Handling

If a sub-skill fails (network error, crash), its findings are skipped and the
orchestrator continues with the remaining skills. A warning note is included in
the report metadata.
