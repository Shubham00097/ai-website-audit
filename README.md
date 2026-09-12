# Brand AI Readiness Audit

> **Adobe University Hackathon 2026 — Round 3** · Agent Skill Marketplace

Audit any website for **AI discoverability** and **on-site engagement** in seconds.  
Point the tool at a URL — get back a structured JSON report with concrete findings, evidence, severity ratings, and actionable fixes.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Skills & Checks](#skills--checks)
- [Output Format](#output-format)
- [CLI Reference](#cli-reference)
- [Running Tests](#running-tests)
- [Design Principles](#design-principles)
- [Severity Levels](#severity-levels)
- [allowed-tools Decision](#allowed-tools-decision)
- [Source Attribution](#source-attribution)
- [Repository](#repository)

---

## Quick Start

**Requirements:** Python 3.8+

```bash
# 1. Install runtime dependencies
pip install -r requirements.txt

# 2. Run a full audit (JSON + stdout)
python skills/audit-orchestrator/scripts/orchestrator.py https://yoursite.com --pretty

# 3. Generate an HTML report alongside the JSON
python skills/audit-orchestrator/scripts/orchestrator.py https://yoursite.com --pretty --html
```

Results are saved to `audit_report.json` (and `audit_report.html` if `--html` is passed).  
A typical audit completes in **3–13 seconds** across all four skills running in parallel.

---

## Architecture

```
brand-ai-readiness-audit/
│
├── marketplace.json               # Marketplace manifest (entrypoint declared)
├── requirements.txt               # Runtime: requests, beautifulsoup4, python-dateutil
├── requirements-dev.txt           # Dev/test: pytest, jsonschema
├── make_submission.ps1            # Submission packaging script (cleans + zips)
│
├── shared/                        # Cross-skill utilities — zero duplication
│   ├── http_client.py             # GET/HEAD with connection pooling & per-host rate limiting
│   ├── html_utils.py              # HTML fetching and BeautifulSoup helpers
│   ├── url_utils.py               # URL normalisation and validation
│   ├── findings.py                # Finding dataclass, sort, dedup, severity promotion
│   └── js_render_detector.py      # Static JS-render gap detection (SPA/CSR awareness)
│
├── skills/
│   ├── audit-orchestrator/        # [ENTRYPOINT] Runs all skills concurrently, merges output
│   │   ├── scripts/
│   │   │   ├── orchestrator.py        # Main CLI runner
│   │   │   └── render_html.py         # Self-contained HTML report renderer
│   │   └── references/
│   │       ├── audit_schema.json      # JSON Schema for output validation
│   │       └── severity_matrix.md     # Severity assignment rules
│   │
│   ├── bot-crawlability-audit/    # Skill 1 — AI crawler access
│   │   ├── scripts/
│   │   │   ├── check_crawlers.py      # Main entry: robots.txt + live probes
│   │   │   ├── robots_parser.py       # robots.txt parsing logic
│   │   │   └── waf_detector.py        # WAF/CDN header fingerprinting
│   │   └── references/
│   │       ├── ai_user_agents.json    # 22 AI crawler User-Agent registry
│   │       └── waf_fingerprints.json  # 15 WAF/CDN signature patterns
│   │
│   ├── structured-data-audit/     # Skill 2 — Schema.org & entity identity
│   │   ├── scripts/check_schema.py
│   │   └── references/
│   │       ├── schema_templates.json  # 8 ready-to-use JSON-LD templates
│   │       └── ymyl_types.json        # YMYL entity type list
│   │
│   ├── citability-freshness-audit/  # Skill 3 — Content quality & cloaking detection
│   │   ├── scripts/check_citability.py
│   │   └── references/
│   │       ├── citability_rubric.md       # 5-dimension citability scoring rubric
│   │       └── injection_signatures.json  # AI cloaking pattern library
│   │
│   └── engagement-ux-audit/       # Skill 4 — On-site UX signals
│       ├── scripts/check_engagement.py
│       └── references/
│           └── ux_heuristics.md           # UX heuristic rules and thresholds
│
└── tests/                         # 52 automated tests (pytest)
    ├── fixtures/                   # Synthetic HTML pages for isolated unit tests
    │   ├── modal_page.html
    │   ├── rich_page.html
    │   ├── spa_shell.html
    │   └── stale_page.html
    ├── test_citability_cloaking.py              # CSS-hidden text, comment injection, zero-width chars
    ├── test_citability_js_gap.py                # SPA content suppression vs SSR
    ├── test_date_parsing.py                     # ISO 8601 with TZ offsets, staleness detection
    ├── test_dedup.py                            # Cross-skill deduplication, severity promotion
    ├── test_determinism.py                      # Sort stability, renumbered F-IDs
    ├── test_html_utils.py                       # Soup helpers, noscript exclusion
    ├── test_js_render_detector.py               # Framework detection (Next.js, React, Angular)
    ├── test_orchestrator_partial_failure.py     # Graceful degradation + JSON Schema validation
    ├── test_orchestrator_render_gap_discount.py # Render-gap confidence discounting
    ├── test_proactive_suggestions.py            # Proactive improvement suggestions
    ├── test_rate_limiting.py                    # Per-host throttle, cross-host independence
    ├── test_schema_corroboration.py             # sameAs corroboration checks
    └── test_schema_js_gap.py                    # Structured data + JS-render gap interaction
```

---

## Skills & Checks

### Skill 1 — `bot-crawlability-audit`

| Check | Severity if Failed |
|---|:---:|
| `robots.txt` accessible | medium |
| AI crawlers allowed in `robots.txt` | high |
| Live bot probe matches `robots.txt` (declared vs. actual) | **critical** |
| `/llms.txt` present | medium |
| `/sitemap.xml` reachable | medium |

### Skill 2 — `structured-data-audit`

| Check | Severity if Failed |
|---|:---:|
| Any structured data present (JSON-LD, Microdata, RDFa) | high |
| Key schema types present (Organization, Article, Product, FAQ…) | high |
| Required fields populated per schema type | high |
| `sameAs` links alive (HEAD check) | high |
| `sameAs` placeholder (`#`) detected | **critical** |
| Entity disambiguation (Wikidata, Wikipedia, LinkedIn) | medium |
| YMYL schema without credential signals | **critical** |
| JS-render gap → findings annotated with reduced confidence | annotation |

### Skill 3 — `citability-freshness-audit`

| Check | Severity if Failed |
|---|:---:|
| Answer-like content blocks (≥ 20 words) | medium |
| Statistical density (numbers, dates, named entities) | medium |
| Content freshness (`datePublished` / `dateModified`) | high |
| Author attribution | medium |
| Outbound citations | medium |
| CSS-hidden text blocks (cloaking) | **critical** |
| HTML comment LLM injection | **critical** |
| Zero-width Unicode characters | **critical** |
| JS-render gap → content checks suppressed | finding |

### Skill 4 — `engagement-ux-audit`

| Check | Severity if Failed |
|---|:---:|
| Exactly one `<h1>` on the page | high |
| Heading hierarchy (no skipped levels) | medium |
| Meta description present and adequately long | medium |
| Content scannability (lists/tables on long pages) | medium |
| Call-to-action element present | high |
| Navigation element present | high |
| Mobile viewport meta tag | high |
| Image alt text coverage | medium |
| `og:title` / `og:description` | medium |
| `og:image` | low |
| JS-render gap detected | finding |

---

## Output Format

The report is a JSON object saved to `audit_report.json`. A real example from auditing `wikipedia.org`:

```json
{
  "site": "www.wikipedia.org",
  "audited_at": "2026-09-06T13:59:32Z",
  "summary": {
    "headline": "1 critical finding(s) detected, primarily in AI Crawler Access.",
    "total_findings": 7,
    "critical": 1,
    "high": 2,
    "medium": 4,
    "low": 0
  },
  "root_causes": [
    { "cause": "crawler_access",  "label": "AI Crawler Access",             "count": 3 },
    { "cause": "content_freshness", "label": "Content Freshness",           "count": 1 },
    { "cause": "entity_identity", "label": "Structured Data & Entity Identity", "count": 1 }
  ],
  "findings": [
    {
      "id": "F-001",
      "title": "Googlebot blocked by server despite robots.txt Allow",
      "severity": "critical",
      "evidence": "robots.txt declares Allow: / for Googlebot. Live HTTP GET returned 403.",
      "confidence": "live HTTP probe",
      "suggested_action": {
        "summary": "Check WAF/CDN firewall rules blocking the Googlebot User-Agent string.",
        "priority": "high"
      }
    }
  ],
  "metadata": {
    "skills_run": ["bot-crawlability-audit", "citability-freshness-audit", "engagement-ux-audit", "structured-data-audit"],
    "skills_failed": [],
    "duration_seconds": 3.52
  }
}
```

Each finding includes an `id`, `title`, `severity`, `evidence` string, `confidence` label (`static heuristic` or `live HTTP probe`), and a `suggested_action` with a concrete fix and priority.

---

## CLI Reference

```bash
# Full audit — saves audit_report.json and prints to stdout
python skills/audit-orchestrator/scripts/orchestrator.py https://example.com

# Pretty-printed output, no file saved
python skills/audit-orchestrator/scripts/orchestrator.py https://example.com --pretty --stdout-only

# Custom output path
python skills/audit-orchestrator/scripts/orchestrator.py https://example.com --output my_report.json --pretty

# Generate HTML report alongside JSON
python skills/audit-orchestrator/scripts/orchestrator.py https://example.com --pretty --html

# Run an individual skill directly
python skills/bot-crawlability-audit/scripts/check_crawlers.py https://example.com
python skills/structured-data-audit/scripts/check_schema.py https://example.com
python skills/citability-freshness-audit/scripts/check_citability.py https://example.com
python skills/engagement-ux-audit/scripts/check_engagement.py https://example.com
```

---

## Running Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest tests/ -v
```

The test suite has 52 tests covering deduplication, determinism, rate limiting, JS-render gap detection, partial skill failures, schema corroboration, and more.

---

## Design Principles

| Principle | Detail |
|---|---|
| **Read-only** | Only `GET` and `HEAD` requests — no writes, no logins, no mutations |
| **Deterministic** | Rule-based checks; same URL always produces the same finding order (severity → skill prefix → index) |
| **Modular** | Each skill has one responsibility; shared utilities eliminate duplication |
| **Resilient** | If one skill crashes, the rest continue; failures are reported in `metadata.skills_failed` |
| **Generalisable** | No site-specific hardcoding — works correctly on any unseen domain |
| **SPA-aware** | Detects JS-render gaps and suppresses false-positive findings on client-side-rendered pages |
| **Rate-limited** | Per-host 0.25 s politeness delay to avoid triggering HTTP 429s |
| **Fast** | All 4 skills run in parallel; typical audit completes in 3–13 seconds |

---

## Severity Levels

| Level | Meaning |
|:---:|---|
| **critical** | Directly prevents an AI from accessing or citing the site |
| **high** | Significantly reduces AI discoverability or user engagement |
| **medium** | Reduces AI citability or engagement quality |
| **low** | Minor improvement opportunity |

---

## `allowed-tools` Decision

Per the [agentskills.io specification](https://agentskills.io/specification) (experimental field), each skill's `SKILL.md` declares `allowed-tools: Read Bash`.

- **Read** — Skills load reference data files (JSON templates, signature databases, heuristic rules).
- **Bash** — The runtime invokes Python scripts that make HTTP requests via the `requests` library. There is no separate `http_request` tool in the spec; network access happens through the Python runtime invoked via Bash.

`marketplace.json` does not declare a top-level `allowed_tools` because the spec defines this field per-skill in `SKILL.md`, not at the package level.

---

## Repository

- **Repository ID**: [Shubham00097/ai-website-audit](https://github.com/Shubham00097/ai-website-audit)
- **Author**: Shubham Kumar ([@Shubham00097](https://github.com/Shubham00097))

