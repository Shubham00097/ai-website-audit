# Brand AI Readiness Audit — Implementation Plan
### Adobe University Hackathon 2026, Round 3: "Build the Agent Skill Marketplace"

---

## Overview

Build a fully spec-compliant, production-grade **Agent Skill Marketplace** that audits any website's AI discoverability and on-site engagement. The tool must:

- Accept a URL, run a silent read-only inspection, and emit a **structured JSON findings report** in under 2 minutes.
- Be packaged as multiple composable **SKILL.md-based skills** conforming to the `agentskills.io` standard.
- Generalize to **any unseen domain** without site-specific hardcoding.
- Stay under **50 MB** (Python stdlib + minimal dependencies).

---

## Open Questions

> [!IMPORTANT]
> Confirm before building:
> - **Python-only or allow Node.js scripts?** (Plan assumes Python 3, stdlib + `requests` + `beautifulsoup4`)
> - **Do you want a simple CLI demo run before the final commit?** (e.g., `python orchestrator.py https://adobe.com`)
> - **Should the final JSON report also be saved to a `.json` file, or only printed to stdout?**

---

## Directory Structure (Final Target Layout)

```
d:\ai-website-audit\
├── marketplace.json
├── README.md
├── requirements.txt
│
└── skills/
    ├── audit-orchestrator/             # [ENTRYPOINT SKILL]
    │   ├── SKILL.md
    │   ├── scripts/
    │   │   └── orchestrator.py
    │   └── references/
    │       ├── audit_schema.json
    │       └── severity_matrix.md
    │
    ├── bot-crawlability-audit/         # [SKILL 1]
    │   ├── SKILL.md
    │   ├── scripts/
    │   │   └── check_crawlers.py
    │   └── references/
    │       ├── ai_user_agents.json
    │       └── waf_fingerprints.json
    │
    ├── structured-data-audit/          # [SKILL 2]
    │   ├── SKILL.md
    │   ├── scripts/
    │   │   └── check_schema.py
    │   └── references/
    │       ├── schema_templates.json
    │       └── ymyl_types.json
    │
    ├── citability-freshness-audit/     # [SKILL 3]
    │   ├── SKILL.md
    │   ├── scripts/
    │   │   └── check_citability.py
    │   └── references/
    │       ├── citability_rubric.md
    │       └── injection_signatures.json
    │
    └── engagement-ux-audit/            # [SKILL 4]
        ├── SKILL.md
        ├── scripts/
        │   └── check_engagement.py
        └── references/
            └── ux_heuristics.md
```

---

## Proposed Changes

---

### Root Level Files

#### [NEW] `marketplace.json`
Top-level manifest declaring all skills, the entrypoint, metadata, and runtime requirements per `agentskills.io`.

```json
{
  "name": "brand-ai-readiness-audit",
  "version": "1.0.0",
  "description": "Audits any website for AI discoverability and on-site engagement.",
  "entrypoint": "skills/audit-orchestrator",
  "skills": [
    "skills/audit-orchestrator",
    "skills/bot-crawlability-audit",
    "skills/structured-data-audit",
    "skills/citability-freshness-audit",
    "skills/engagement-ux-audit"
  ],
  "runtime": "python3",
  "min_python": "3.8"
}
```

#### [MODIFY] `README.md`
Full architecture guide: skill roles, composition flow, CLI usage, and sample output.

#### [NEW] `requirements.txt`
```
requests>=2.28
beautifulsoup4>=4.12
```

---

### Skill 1 — `audit-orchestrator` (Entrypoint)

#### [NEW] `skills/audit-orchestrator/SKILL.md`
- YAML frontmatter: `name`, `description`, `version`, `entrypoint`, `allowed_tools`, `parameters`
- Body: Step-by-step procedure to:
  1. Accept a target URL as input
  2. Call each of the 4 sub-skill Python scripts in parallel
  3. Collect their `findings[]` arrays
  4. Merge, deduplicate, and sort findings by severity (`critical > high > medium > low`)
  5. Emit the exact required JSON output schema

#### [NEW] `skills/audit-orchestrator/scripts/orchestrator.py`
- CLI: `python orchestrator.py <url>`
- Invokes all 4 sub-scripts via imports (or subprocesses)
- Normalizes findings into a single flat list
- Generates `summary` (counts by severity)
- Prints final JSON to stdout + saves `audit_report.json`

#### [NEW] `skills/audit-orchestrator/references/audit_schema.json`
Formal JSON Schema (Draft-07) for validating the output report structure.

#### [NEW] `skills/audit-orchestrator/references/severity_matrix.md`
Rules for assigning severity levels (`critical`, `high`, `medium`, `low`) to each finding type.

---

### Skill 2 — `bot-crawlability-audit`

#### [NEW] `skills/bot-crawlability-audit/SKILL.md`
Procedure for auditing AI crawler access, robot rules, and agent readiness.

#### [NEW] `skills/bot-crawlability-audit/scripts/check_crawlers.py`

**Checks implemented (from `geo-reporter`):**

| Check | Logic |
|---|---|
| `robots.txt` parsing | Fetch and parse `/robots.txt`. Check `Disallow`/`Allow` rules for 22 AI bot identities |
| Live reachability probe | HTTP `GET` with each AI crawler User-Agent. Record status code (`200`, `403`, `429`, `402`) |
| Declared vs. Actual mismatch | `robots.txt` says `Allow` but live response is `403` → **Critical** |
| `llms.txt` presence | `HEAD /llms.txt` and `/llms-full.txt`. Missing → Medium |
| `sitemap.xml` presence | `HEAD /sitemap.xml`. Missing → Medium |
| WAF fingerprinting | Match response headers against 15 WAF/CDN signatures. Name the product in evidence |
| HTTP 402 pay-per-crawl | Classified separately as informational, not a block |

**AI Crawler User-Agent Registry (22 bots, 4 categories):**
- *Live Retrieval:* `ChatGPT-User`, `Claude-User`, `Perplexity-User`, `MistralAI-User`, `Google-Agent`
- *Search Index:* `OAI-SearchBot`, `Claude-SearchBot`, `PerplexityBot`, `DuckAssistBot`, `Amazonbot`
- *Traditional Search:* `Googlebot`, `Bingbot`
- *Training Crawlers:* `GPTBot`, `ClaudeBot`, `CCBot`, `Google-Extended`, `Bytespider`, `Meta-ExternalAgent`

#### [NEW] `skills/bot-crawlability-audit/references/ai_user_agents.json`
Registry of all 22 crawler identities with category and owner metadata.

#### [NEW] `skills/bot-crawlability-audit/references/waf_fingerprints.json`
15 WAF/CDN header signature patterns (Cloudflare, Akamai, AWS WAF, Imperva, Fastly, Azure Front Door, etc.).

---

### Skill 3 — `structured-data-audit`

#### [NEW] `skills/structured-data-audit/SKILL.md`
Procedure for validating structured data, entity identity, and disambiguation.

#### [NEW] `skills/structured-data-audit/scripts/check_schema.py`

**Checks implemented (from `geo-reporter` + `ai-visibility-audit`):**

| Check | Logic |
|---|---|
| JSON-LD extraction | Parses all `<script type="application/ld+json">` blocks |
| Schema type presence | Detects `Organization`, `Product`, `Article`, `FAQPage`, `LocalBusiness`, `WebSite` |
| Required field validation | `Article` needs `author`, `datePublished`, `image`. Missing required fields → High |
| `sameAs` liveness | HEAD-checks every `sameAs` URL. Dead links → High. Placeholder `#` → Critical |
| `@id` consistency | Verifies `@id` values are consistent across pages |
| YMYL guard | `LegalService`, `MedicalWebPage`, `Physician` without verified credentials → Critical |
| Entity disambiguation | Missing Wikidata/Wikipedia/LinkedIn in `sameAs` → Medium |
| Microdata & RDFa detection | Detects alternative structured data if JSON-LD is absent |

#### [NEW] `skills/structured-data-audit/references/schema_templates.json`
8 ready-to-adapt JSON-LD templates: `Organization`, `LocalBusiness`, `Article+Author`, `Product`, `FAQPage`, `SoftwareApplication`, `WebSite+SearchAction`, `VideoObject`

#### [NEW] `skills/structured-data-audit/references/ymyl_types.json`
List of YMYL entity types requiring credential verification before recommendation.

---

### Skill 4 — `citability-freshness-audit`

#### [NEW] `skills/citability-freshness-audit/SKILL.md`
Procedure for content extractability, AI citability scoring, freshness, and cloaking detection.

#### [NEW] `skills/citability-freshness-audit/scripts/check_citability.py`

**Checks implemented (from `geo-reporter`):**

| Check | Logic |
|---|---|
| Answer block scorer | Paragraphs ≥20 words scored: answer quality (30pts), self-containment (25pts), readability (20pts), statistical density (15pts), uniqueness (10pts) |
| Statistical density | Low numbers/dates/entities per paragraph → Medium |
| Content freshness | `datePublished`/`dateModified` >18 months old → High |
| Author byline | Missing `author` meta or byline pattern → Medium |
| Trust signals | Low outbound citations and statistics → Medium |
| AI cloaking detector | CSS-hidden text (≥8 words), HTML comment LLM instructions, zero-width Unicode → Critical |
| Blog cadence | Last 10 posts gap >90 days → Low |

#### [NEW] `skills/citability-freshness-audit/references/citability_rubric.md`
Full scoring rubric with dimension weights and score bands.

#### [NEW] `skills/citability-freshness-audit/references/injection_signatures.json`
Regex patterns for AI prompt injection and cloaking detection.

---

### Skill 5 — `engagement-ux-audit`

#### [NEW] `skills/engagement-ux-audit/SKILL.md`
Procedure for on-site visitor orientation, content readability, and interaction quality.

#### [NEW] `skills/engagement-ux-audit/scripts/check_engagement.py`

**Checks implemented (from `website-seo-audit` + `ai-visibility-audit`):**

| Check | Logic |
|---|---|
| H1 count | Exactly 1 `<h1>` required. Zero or multiple → High |
| Heading hierarchy | Skipped heading levels (h1→h3 with no h2) → Medium |
| Above-the-fold clarity | `<meta name="description">` and `<h1>` text clarity and length → Medium |
| Readability | Average words per sentence >25 → Medium |
| Content scannability | No `<ul>`, `<ol>`, `<table>` on long page → Medium |
| CTA presence | No action verbs in `<a>`, `<button>`, `<form>` → High |
| Internal navigation | No `<nav>` or meaningful internal link set → High |
| Mobile viewport | Missing `<meta name="viewport">` → High |
| Image alt text | Informational images without `alt` → Medium |
| Open Graph tags | Missing `og:title`, `og:description`, `og:image` → Medium |

#### [NEW] `skills/engagement-ux-audit/references/ux_heuristics.md`
Nielsen's 10 heuristics adapted for AI-era engagement with scoring thresholds.

---

## Final Report Output Schema

```json
{
  "site": "example.com",
  "audited_at": "2026-09-20T14:32:00Z",
  "summary": {
    "total_findings": 6,
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 0
  },
  "findings": [
    {
      "id": "F-001",
      "title": "GPTBot blocked by Cloudflare WAF despite robots.txt Allow",
      "severity": "critical",
      "evidence": "robots.txt declares 'Allow: /' for GPTBot. Live probe returns HTTP 403 with CF-Ray header. Cloudflare WAF identified via 'cf-cache-status' and 'server: cloudflare' response headers.",
      "suggested_action": {
        "summary": "Log in to Cloudflare dashboard → Security → WAF → Custom Rules and remove or whitelist the rule blocking GPTBot.",
        "priority": "high"
      }
    }
  ]
}
```

---

## Technical Guardrails

| Constraint | Implementation |
|---|---|
| **Read-only** | Only `GET` / `HEAD` requests. No `POST`, `PUT`, or authenticated actions |
| **Respects `robots.txt`** | Content crawling follows `robots.txt` Googlebot rules; bot probing uses explicit UA headers only |
| **Performance** | All 4 skills run in parallel via `concurrent.futures.ThreadPoolExecutor`. Target < 2 minutes |
| **Package size** | Only `requests` + `beautifulsoup4`. No ML models, no Chromium. Well under 50 MB |
| **Deterministic** | All checks are rule-based (no LLM scoring). Two runs on same page = identical output |
| **Generalization** | Zero site-specific hardcoding. All patterns loaded from `references/` files |

---

## Verification Plan

### Automated Tests

```bash
# Run full audit on a live site
python skills/audit-orchestrator/scripts/orchestrator.py https://adobe.com

# Run individual sub-skill scripts
python skills/bot-crawlability-audit/scripts/check_crawlers.py https://adobe.com
python skills/structured-data-audit/scripts/check_schema.py https://adobe.com
python skills/citability-freshness-audit/scripts/check_citability.py https://adobe.com
python skills/engagement-ux-audit/scripts/check_engagement.py https://adobe.com
```

### Manual Verification
- Run end-to-end on 3 diverse live domains (e.g., `adobe.com`, a local business, a news site)
- Confirm all 4 sub-scripts individually emit valid partial findings arrays
- Confirm orchestrator correctly merges and sorts findings by severity
- Verify total runtime < 2 minutes per site
- Confirm final commit pushed to `https://github.com/Shubham00097/ai-website-audit` on `main`

---

## Build Order (3 Phases)

```
Phase 1: Scaffold                 Phase 2: Core Logic                Phase 3: Polish & Push
─────────────────                 ────────────────────               ──────────────────────
[ ] marketplace.json              [ ] check_crawlers.py              [ ] Final README.md
[ ] requirements.txt              [ ] check_schema.py                [ ] Test on 3+ live sites
[ ] Skill directories             [ ] check_citability.py            [ ] Validate JSON schema
[ ] All SKILL.md files            [ ] check_engagement.py            [ ] git commit + push
[ ] All references/ files         [ ] orchestrator.py                [ ] Verify GitHub push
```

---

## Source Attribution

| Repository | What We Adopt |
|---|---|
| [`internet-and-sons/geo-reporter`](https://github.com/internet-and-sons/geo-reporter) | 22 AI crawler User-Agent registry, Declared vs. Actual WAF mismatch detection, Citability 5-dimension scorer, AI cloaking/injection detector, Agent endpoint probes (`llms.txt`, `agents.json`) |
| [`Almontas/ai-visibility-audit`](https://github.com/Almontas/ai-visibility-audit) | 6-category scoring model, Brand trust & E-E-A-T signals, Content freshness & staleness checks, Engagement + readability metrics |
| [`zxhydfzr/website-seo-audit`](https://github.com/zxhydfzr/website-seo-audit) | Zero-dependency Python architecture, `agentskills.io`-compliant `SKILL.md` format, Deterministic evidence-backed reporting, Heading hierarchy & SEO checks |
