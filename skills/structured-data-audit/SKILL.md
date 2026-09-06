---
name: structured-data-audit
version: "1.0.0"
description: >
  Validates structured data markup (JSON-LD, Microdata, RDFa) on the website.
  Checks schema.org type presence, required field completeness, sameAs link
  liveness, and entity disambiguation.
role: sub-skill
parameters:
  - name: url
    type: string
    required: true
    description: The website URL to audit
allowed_tools:
  - read_file
  - http_request
---

# Structured Data Audit

## Purpose

AI systems use structured data to understand what a website is, what it offers,
and whether to trust it. Missing or malformed schema.org markup causes AI
assistants to misidentify, skip, or incorrectly summarise website content.

## Checks Performed

| Check | Severity if Failed |
|---|---|
| Any structured data found | high |
| Key schema types present (Organization, etc.) | high |
| Required fields present per schema type | high |
| sameAs links resolve (no dead links) | high |
| sameAs placeholder (#) detected | critical |
| Entity disambiguation links present | medium |
| YMYL schema used without credential signals | critical |

## Schema Templates

Ready-to-use JSON-LD templates for common types: `references/schema_templates.json`

## YMYL Protection

YMYL (Your Money or Your Life) schemas — legal, medical, financial — are never
recommended without verified credentials, as incorrect markup is a manual-action
risk. See `references/ymyl_types.json`.

## How to Run Standalone

```bash
python skills/structured-data-audit/scripts/check_schema.py https://example.com
```
