# Brand AI Readiness Audit

Brand AI Readiness Audit is an Agent Skill Marketplace for evaluating how well a public website can be discovered, understood, cited, and used after an AI referral. Give the entrypoint a URL and it performs read-only HTTP and static-HTML checks, returning a structured JSON report with evidence and practical fixes.

## Skills

### `skills/audit-orchestrator`

The marketplace entrypoint. It validates the URL, detects client-rendering gaps once for the whole audit, runs the four specialist skills concurrently, and produces the final JSON report. It can also render a self-contained HTML report.

### `skills/bot-crawlability-audit`

Checks whether AI crawlers can actually reach the website. It parses `robots.txt`, checks AI user-agent permissions, performs permitted live bot probes, identifies possible WAF/CDN blocking, and checks `llms.txt` and sitemap availability.

### `skills/structured-data-audit`

Checks JSON-LD, Microdata, and RDFa for schema completeness and entity identity. It validates required fields, tests `sameAs` links, looks for authoritative disambiguation sources, detects inconsistent facts across linked sources, and identifies YMYL schema risk.

### `skills/citability-freshness-audit`

Evaluates whether page content is easy for AI systems to quote and trust. It scores substantive text for citability, checks dates, authorship, and outbound citations, and detects manipulation signals such as hidden text, prompt-injection comments, and zero-width characters.

### `skills/engagement-ux-audit`

Checks the page experience for visitors referred by AI. It evaluates heading structure, metadata, scan-friendly content, CTAs, navigation, mobile viewport configuration, image alt text, and Open Graph metadata.

## How the report is composed

Run the audit with:

```bash
python skills/audit-orchestrator/scripts/orchestrator.py https://example.com --pretty --html
```

The orchestrator runs the four skills concurrently, merges their findings, removes duplicates, sorts by severity, and renumbers them as `F-001`, `F-002`, and so on. It records root causes, successful and failed skills, run time, and relevant proactive improvements separately from defects. When static HTML indicates a client-rendered page, HTML-dependent findings are clearly marked for manual review and discounted consistently; network-based crawler checks remain unchanged.

See [architecture.md](architecture.md) for the component-level design and operational boundaries.
