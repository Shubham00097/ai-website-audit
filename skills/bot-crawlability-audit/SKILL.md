---
name: bot-crawlability-audit
version: "1.0.0"
description: >
  Audits whether AI crawlers can actually reach the website.
  Checks robots.txt rules, performs live HTTP probes with real AI bot
  User-Agents, detects WAF/CDN blocking, and checks for llms.txt.
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

# Bot Crawlability Audit

## Purpose

Determine whether AI search engines and language model crawlers can actually
reach and index this website. A site can declare open access in `robots.txt`
while silently blocking AI bots at the WAF or CDN layer.

## Checks Performed

| Check | Severity if Failed |
|---|---|
| robots.txt is accessible | medium |
| Key AI crawlers are allowed by robots.txt | high |
| Live HTTP probe matches robots.txt declaration | critical |
| /llms.txt file present | medium |
| /sitemap.xml present | medium |
| WAF/CDN identified that may be blocking bots | high |

## Declared vs. Actual Mismatch

The highest-value finding this skill produces. If `robots.txt` declares
`Allow: /` for a bot but a live HTTP request with that bot's User-Agent
returns HTTP 403 or 429, this is a **critical** finding — the site is
silently blocking the crawler despite claiming otherwise.

## AI Crawler Categories

Detailed User-Agent registry: `references/ai_user_agents.json`
WAF/CDN fingerprint patterns: `references/waf_fingerprints.json`

## How to Run Standalone

```bash
python skills/bot-crawlability-audit/scripts/check_crawlers.py https://example.com
```
