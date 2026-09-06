---
name: citability-freshness-audit
version: "1.0.0"
description: >
  Scores whether the website's content is extractable and quotable by AI systems.
  Checks answer-block quality, content freshness, author trust signals, and
  detects AI cloaking or prompt injection attempts.
role: sub-skill
parameters:
  - name: url
    type: string
    required: true
    description: The website URL to audit
allowed-tools: Read Bash
---

# Citability & Freshness Audit

## Purpose

A page can rank well in Google and still never be quoted by an AI assistant.
This skill audits whether content blocks are written in a way that AI systems
can extract, trust, and cite — and flags content that is stale, unattributed,
or manipulative.

## Checks Performed

| Check | Severity if Failed |
|---|---|
| Content has answer-like paragraphs (≥20 words) | medium |
| Paragraphs contain statistical/factual density | medium |
| Content freshness (datePublished/dateModified) | high |
| Author byline or attribution present | medium |
| Outbound citation/trust signals present | medium |
| AI cloaking: CSS-hidden text detected | critical |
| AI cloaking: HTML comment LLM instructions | critical |
| AI cloaking: zero-width Unicode characters | critical |

## Citability Scoring Rubric

Full rubric with dimension weights: `references/citability_rubric.md`

Dimensions scored per content block:
1. Answer block quality (30 pts) — Does the paragraph start with a direct answer?
2. Self-containment (25 pts) — Does it make sense in isolation?
3. Structural readability (20 pts) — Lists, tables, scannable formatting
4. Statistical density (15 pts) — Numbers, dates, named entities
5. Uniqueness (10 pts) — Original data vs. restated consensus

## AI Cloaking Detection

Known patterns: `references/injection_signatures.json`
Findings are conservative — flagged as *signals for review*, not proof of intent.

## How to Run Standalone

```bash
python skills/citability-freshness-audit/scripts/check_citability.py https://example.com
```
