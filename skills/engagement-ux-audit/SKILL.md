---
name: engagement-ux-audit
version: "1.0.0"
description: >
  Audits on-site visitor engagement and orientation quality.
  Checks heading hierarchy, content readability, CTA presence,
  navigation, Open Graph metadata, mobile viewport, and JS-render gaps
  (detects pages where content is client-side rendered and invisible to AI bots).
role: sub-skill
parameters:
  - name: url
    type: string
    required: true
    description: The website URL to audit
allowed-tools: Read Bash
---

# Engagement & UX Audit

## Purpose

When AI systems drive traffic to a website, visitors arrive with high intent.
Poor orientation, unclear headings, missing CTAs, and bad metadata cause
immediate abandonment — wasting the AI referral. This skill audits the
on-site experience that visitors encounter.

## Checks Performed

| Check | Severity if Failed |
|---|---|
| Exactly one <h1> tag present | high |
| Heading levels not skipped (h1→h2→h3) | medium |
| Meta description present and meaningful | medium |
| Page content is scannable (lists/tables) | medium |
| Clear CTA (button/link with action verb) | high |
| Navigation element present | high |
| Mobile viewport meta tag present | high |
| Images have alt text | medium |
| Open Graph title present | medium |
| Open Graph description present | medium |
| Open Graph image present | low |

## UX Heuristics Reference

Scoring thresholds and heuristic rules: `references/ux_heuristics.md`

## How to Run Standalone

```bash
python skills/engagement-ux-audit/scripts/check_engagement.py https://example.com
```
