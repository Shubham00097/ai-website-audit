# Brand AI Readiness Audit
### Agent Skill Marketplace — Adobe University Hackathon 2026, Round 3

Audits any website for **AI discoverability** and **on-site engagement**. Point it at a URL, get back a structured JSON report with concrete findings, evidence, severity ratings, and actionable fixes.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the audit
py skills/audit-orchestrator/scripts/orchestrator.py https://yoursite.com --pretty

# 3. View the saved report
type audit_report.json

# 4. (Optional) Generate an HTML report
py skills/audit-orchestrator/scripts/orchestrator.py https://yoursite.com --pretty --html
```

---

## Architecture

```
brand-ai-readiness-audit/
├── marketplace.json                    # Marketplace manifest (entrypoint declared)
├── requirements.txt                    # requests, beautifulsoup4
├── make_submission.ps1                 # Submission packaging script
├── README.md
│
├── shared/                             # Shared utilities (no duplication)
│   ├── http_client.py                  # GET/HEAD with connection pooling, per-host rate limiting
│   ├── html_utils.py                   # HTML fetching and BeautifulSoup helpers
│   ├── url_utils.py                    # URL normalisation and validation
│   ├── findings.py                     # Finding dataclass (with cause_tag, confidence), sort, dedup
│   └── js_render_detector.py           # Static JS-render gap detection (SPA/CSR awareness)
│
└── skills/
    ├── audit-orchestrator/             # [ENTRYPOINT] Composes all skills
    │   ├── SKILL.md
    │   ├── scripts/
    │   │   ├── orchestrator.py         # Main CLI runner
    │   │   └── render_html.py          # HTML report renderer (--html flag)
    │   └── references/
    │       ├── audit_schema.json       # JSON Schema for report validation
    │       └── severity_matrix.md      # Severity assignment rules
    │
    ├── bot-crawlability-audit/         # Skill 1: AI crawler access
    │   ├── SKILL.md
    │   ├── scripts/
    │   │   ├── check_crawlers.py       # Main entry: robots.txt + live probes
    │   │   ├── robots_parser.py        # robots.txt parsing logic
    │   │   └── waf_detector.py         # WAF/CDN header fingerprinting
    │   └── references/
    │       ├── ai_user_agents.json     # 22 AI crawler User-Agent registry
    │       └── waf_fingerprints.json   # 15 WAF/CDN signature patterns
    │
    ├── structured-data-audit/          # Skill 2: Schema.org & entity identity
    │   ├── SKILL.md
    │   ├── scripts/check_schema.py
    │   └── references/
    │       ├── schema_templates.json   # 8 ready-to-use JSON-LD templates
    │       └── ymyl_types.json         # YMYL entity type list
    │
    ├── citability-freshness-audit/     # Skill 3: Content quality & cloaking
    │   ├── SKILL.md
    │   ├── scripts/check_citability.py
    │   └── references/
    │       ├── citability_rubric.md    # 5-dimension citability scoring rubric
    │       └── injection_signatures.json # AI cloaking pattern library
    │
    └── engagement-ux-audit/            # Skill 4: On-site UX
        ├── SKILL.md
        ├── scripts/check_engagement.py
        └── references/
            └── ux_heuristics.md       # UX heuristic rules and thresholds
```

---

## What Each Skill Checks

### Skill 1: `bot-crawlability-audit`
| Check | Finding if Failed |
|---|---|
| robots.txt accessible | medium |
| AI crawlers allowed in robots.txt | high |
| Live bot probe matches robots.txt (declared vs. actual) | **critical** |
| /llms.txt present | medium |
| /sitemap.xml present | medium |

### Skill 2: `structured-data-audit`
| Check | Finding if Failed |
|---|---|
| Any structured data present | high |
| Key schema types (Organization, Article, Product, FAQ…) | high |
| Required fields per schema type | high |
| sameAs links alive (HEAD check) | high |
| sameAs placeholder (#) | **critical** |
| Entity disambiguation (Wikidata, Wikipedia, LinkedIn) | medium |
| YMYL schema without credential signals | **critical** |
| JS-render gap → reduced confidence on findings | annotation |

### Skill 3: `citability-freshness-audit`
| Check | Finding if Failed |
|---|---|
| Answer-like content blocks (≥20 words) | medium |
| Statistical density (numbers, dates, entities) | medium |
| Content freshness (datePublished/Modified) | high |
| Author attribution | medium |
| Outbound citations | medium |
| CSS-hidden text blocks (cloaking) | **critical** |
| HTML comment LLM injection | **critical** |
| Zero-width Unicode characters | **critical** |
| JS-render gap → content checks suppressed | finding |

### Skill 4: `engagement-ux-audit`
| Check | Finding if Failed |
|---|---|
| Exactly one `<h1>` | high |
| Heading hierarchy (no skipped levels) | medium |
| Meta description present and long enough | medium |
| Content scannability (lists/tables on long pages) | medium |
| Call to Action present | high |
| Navigation element present | high |
| Mobile viewport meta tag | high |
| Image alt text coverage | medium |
| og:title / og:description | medium |
| og:image | low |
| JS-render gap detected | finding |

---

## Output Format

```json
{
  "site": "example.com",
  "audited_at": "2026-09-03T20:07:03Z",
  "summary": {
    "headline": "3 high-severity finding(s) detected, primarily in On-Site Orientation & UX.",
    "total_findings": 12,
    "critical": 0,
    "high": 3,
    "medium": 8,
    "low": 1
  },
  "root_causes": [
    {
      "cause": "onsite_orientation",
      "label": "On-Site Orientation & UX",
      "finding_ids": ["F-001", "F-002", "F-003"],
      "count": 3
    }
  ],
  "findings": [
    {
      "id": "F-001",
      "title": "No structured data found on the page",
      "severity": "high",
      "evidence": "The page contains no JSON-LD, Microdata, or RDFa...",
      "confidence": "static heuristic",
      "suggested_action": {
        "summary": "Add JSON-LD structured data. Start with Organization schema...",
        "priority": "high",
        "snippet": "{ \"@context\": \"https://schema.org\", ... }"
      }
    }
  ],
  "metadata": {
    "skills_run": ["bot-crawlability-audit", "structured-data-audit", ...],
    "skills_failed": [],
    "duration_seconds": 4.2
  }
}
```

---

## CLI Usage

```bash
# Full audit (saves audit_report.json + prints to stdout)
py skills/audit-orchestrator/scripts/orchestrator.py https://example.com

# Pretty-printed, no file save
py skills/audit-orchestrator/scripts/orchestrator.py https://example.com --pretty --stdout-only

# Custom output path
py skills/audit-orchestrator/scripts/orchestrator.py https://example.com --output my_report.json --pretty

# Generate HTML report alongside JSON
py skills/audit-orchestrator/scripts/orchestrator.py https://example.com --pretty --html

# Run individual skills
py skills/bot-crawlability-audit/scripts/check_crawlers.py https://example.com
py skills/structured-data-audit/scripts/check_schema.py https://example.com
py skills/citability-freshness-audit/scripts/check_citability.py https://example.com
py skills/engagement-ux-audit/scripts/check_engagement.py https://example.com
```

---

## Design Principles

- **Read-only**: Only `GET` and `HEAD` requests. No writes, no logins, no mutations.
- **Deterministic**: All checks are rule-based. Same URL → same finding order every time (severity → skill prefix → index).
- **Modular**: Each skill has one responsibility. Shared utilities eliminate duplication.
- **Graceful failures**: If one skill crashes, the others continue.
- **Generalisable**: No site-specific hardcoding. Works on any unseen domain.
- **SPA-aware**: Detects JS-render gaps and suppresses false-positive findings on client-side-rendered pages.
- **Rate-limited**: Per-host politeness delay (0.25s) to avoid triggering 429s.
- **Fast**: All 4 skills run in parallel. Typical audit 10–60 seconds depending on site response times.

---

## Severity Levels

| Level | Meaning |
|---|---|
| **critical** | Directly prevents AI from accessing or citing the site |
| **high** | Significantly reduces AI discoverability or user engagement |
| **medium** | Reduces AI citability or engagement quality |
| **low** | Minor improvement opportunity |

---

## `allowed-tools` Design Decision

Per the [agentskills.io specification](https://agentskills.io/specification) (experimental field), each skill's `SKILL.md` declares `allowed-tools: Read Bash`. This means:

- **Read**: Skills load reference data files (JSON templates, signature databases, heuristic rules).
- **Bash**: The runtime executes Python scripts that make HTTP requests via the `requests` library. There is no separate `http_request` tool in the spec — network access happens through the Python runtime invoked via Bash.

The `marketplace.json` does not declare a top-level `allowed_tools` because the spec defines this field per-skill in `SKILL.md`, not at the package level.

---

## Source Attribution

| Repository | Contribution |
|---|---|
| [internet-and-sons/geo-reporter](https://github.com/internet-and-sons/geo-reporter) | AI crawler registry, declared-vs-actual mismatch, citability scorer, cloaking detection |
| [Almontas/ai-visibility-audit](https://github.com/Almontas/ai-visibility-audit) | Scoring model design, freshness checks, trust signals, engagement metrics |
| [zxhydfzr/website-seo-audit](https://github.com/zxhydfzr/website-seo-audit) | Python architecture pattern, SKILL.md format, heading and SEO checks |
