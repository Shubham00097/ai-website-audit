"""
skills/structured-data-audit/scripts/check_schema.py

Entry point for the structured-data-audit skill.

Checks:
  1. Presence of any JSON-LD structured data
  2. Key schema.org types present (Organization, Product, Article, etc.)
  3. Required fields per schema type
  4. sameAs link liveness (HEAD check)
  5. Entity disambiguation (Wikidata, Wikipedia, LinkedIn in sameAs)
  6. YMYL schema types flagged if no credential signals found

Returns a list of Finding objects.

Usage:
    python check_schema.py https://example.com
    python check_schema.py https://example.com --json
"""
from __future__ import annotations

import json
import os
import re
import sys
import argparse
from typing import Optional

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.url_utils import normalise_url, validate_url
from shared.html_utils import fetch_html_and_parse
from shared.http_client import head
from shared.findings import make_finding, Finding
from shared.js_render_detector import detect_js_render_gap

SKILL_PREFIX = "SCHEMA"

# Required fields per schema type
REQUIRED_FIELDS: dict[str, list[str]] = {
    "Article":           ["headline", "author", "datePublished"],
    "BlogPosting":       ["headline", "author", "datePublished"],
    "NewsArticle":       ["headline", "author", "datePublished"],
    "Product":           ["name", "offers"],
    "Organization":      ["name", "url"],
    "LocalBusiness":     ["name", "address"],
    "FAQPage":           ["mainEntity"],
    "WebSite":           ["name", "url"],
    "SoftwareApplication": ["name", "operatingSystem", "applicationCategory"],
    "VideoObject":       ["name", "description", "thumbnailUrl", "uploadDate"],
    "Event":             ["name", "startDate", "location"],
}

# Entity disambiguation: these domains in sameAs indicate good entity clarity
DISAMBIGUATION_DOMAINS = [
    "wikidata.org", "wikipedia.org", "linkedin.com",
    "crunchbase.com", "github.com", "twitter.com", "facebook.com",
]

_YMYL_PATH = os.path.join(os.path.dirname(__file__), "..", "references", "ymyl_types.json")


def _load_ymyl_types() -> list[str]:
    try:
        with open(_YMYL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [t.lower() for t in data.get("ymyl_types", [])]
    except Exception:
        return []


def _extract_json_ld(soup) -> list[dict]:
    """Extract and parse all JSON-LD blocks from the page."""
    schemas = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, list):
                schemas.extend(data)
            elif isinstance(data, dict):
                schemas.append(data)
        except (json.JSONDecodeError, TypeError):
            continue
    return schemas


def _get_type(schema: dict) -> Optional[str]:
    """Return the @type of a schema, normalised to a string."""
    t = schema.get("@type", "")
    if isinstance(t, list):
        return t[0] if t else None
    return str(t) if t else None


def _check_required_fields(schema: dict, schema_type: str) -> list[str]:
    """Return list of missing required fields for a schema type."""
    required = REQUIRED_FIELDS.get(schema_type, [])
    return [field for field in required if not schema.get(field)]


def _check_same_as(same_as: list[str], findings: list[Finding], idx: list[int]) -> None:
    """Check sameAs links for placeholders and dead links (capped to top 6 to stay responsive)."""
    unique_links = list(dict.fromkeys(same_as))[:6]
    for link in unique_links:
        if link == "#" or not link.startswith("http"):
            findings.append(make_finding(
                skill_prefix=SKILL_PREFIX,
                index=idx[0],
                title="sameAs contains a placeholder link (#)",
                severity="critical",
                evidence=(
                    f"The structured data contains sameAs: '{link}' which is a placeholder. "
                    "AI systems use sameAs links to verify entity identity. "
                    "A placeholder prevents disambiguation."
                ),
                action_summary=(
                    "Replace the placeholder '#' in sameAs with the actual URL of your entity's profile "
                    "(e.g., LinkedIn, Wikipedia, Wikidata, Crunchbase). "
                    "Remove sameAs entries entirely if you don't have a real URL to provide."
                ),
                action_priority="high",
                confidence="static heuristic",
                cause_tag="entity_identity",
            ))
            idx[0] += 1
            continue

        resp = head(link)
        if resp is None or resp.status_code >= 400:
            findings.append(make_finding(
                skill_prefix=SKILL_PREFIX,
                index=idx[0],
                title=f"sameAs link is dead or unreachable: {link[:60]}",
                severity="high",
                evidence=(
                    f"HEAD request to sameAs URL '{link}' returned "
                    f"HTTP {resp.status_code if resp else 'no response'}. "
                    "AI systems follow sameAs links to verify entity identity. "
                    "A dead link prevents disambiguation."
                ),
                action_summary=(
                    f"Update or remove the dead sameAs link: {link}. "
                    "Verify the URL is publicly accessible before adding it to your structured data."
                ),
                action_priority="high",
                confidence="live HTTP probe",
                cause_tag="entity_identity",
            ))
            idx[0] += 1


def _check_entity_disambiguation(same_as: list[str], findings: list[Finding], idx: list[int]) -> None:
    """Check whether sameAs includes at least one strong disambiguation source."""
    found_disambiguation = any(
        any(d in link for d in DISAMBIGUATION_DOMAINS)
        for link in same_as
    )
    if not found_disambiguation:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="No entity disambiguation links in sameAs",
            severity="medium",
            evidence=(
                "The structured data has no sameAs links pointing to authoritative identity sources "
                "(Wikidata, Wikipedia, LinkedIn, Crunchbase). "
                "Without these, AI systems may confuse this entity with similarly-named organisations."
            ),
            action_summary=(
                "Add a sameAs link pointing to your entity's Wikidata item, Wikipedia article, "
                "LinkedIn company page, or Crunchbase profile. "
                "Example: \"sameAs\": \"https://www.linkedin.com/company/your-company\""
            ),
            action_priority="medium",
            confidence="static heuristic",
            cause_tag="entity_identity",
        ))
        idx[0] += 1


_TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "..", "references", "schema_templates.json")

# Annotation suffix for findings on pages with detected JS render gaps.
_JS_GAP_NOTE = (
    " (note: this page appears to use client-side rendering — structured data may "
    "be injected at runtime via JavaScript and invisible to static crawlers. Verify manually.)"
)


def _load_template(schema_type: str) -> str | None:
    """Load a JSON-LD template snippet for B3 copy-pasteable fixes."""
    try:
        with open(_TEMPLATES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        tmpl = data.get("templates", {}).get(schema_type)
        if tmpl:
            return json.dumps(tmpl, indent=2)
    except Exception:
        pass
    return None


def _detect_page_type(soup) -> str | None:
    """
    Simple heuristic to guess the page's schema type for B3 template selection.
    Uses og:type meta tag as the primary signal.
    Returns a schema_templates.json key or None.
    """
    from shared.html_utils import get_og_property
    og_type = get_og_property(soup, "og:type")
    if og_type:
        og_type = og_type.lower()
        if "article" in og_type or "blog" in og_type:
            return "Article"
        if "product" in og_type:
            return "Product"
        if "video" in og_type:
            return "VideoObject"
    # Fallback: default to Organization (safest generic template)
    return "Organization"


def run(url: str) -> list[Finding]:
    """Run the full structured data audit. Returns a list of Finding objects."""
    url = normalise_url(url)
    if not validate_url(url):
        return []

    result = fetch_html_and_parse(url)
    if result is None:
        return []
    html_raw, soup = result

    findings: list[Finding] = []
    idx = [1]
    ymyl_types = _load_ymyl_types()

    # Correction 3: detect JS-render gap for reduced-confidence annotation.
    # JSON-LD is usually in static HTML, but sites using GTM or client-side
    # head-managers may inject it at runtime — we can't assume immunity.
    js_gap = detect_js_render_gap(html_raw, soup)
    is_js_gap = js_gap is not None

    schemas = _extract_json_ld(soup)

    # Also check for Microdata/RDFa as a fallback signal
    has_microdata = bool(soup.find(attrs={"itemscope": True}))
    has_rdfa = bool(soup.find(attrs={"typeof": True}))

    if not schemas and not has_microdata and not has_rdfa:
        # B3: include a copy-pasteable template snippet
        page_type = _detect_page_type(soup)
        snippet = _load_template(page_type) if page_type else None

        evidence = (
            "The page contains no JSON-LD (<script type='application/ld+json'>), "
            "Microdata (itemscope), or RDFa (typeof) structured data. "
            "AI systems rely on structured data to understand entity type, offerings, and identity."
        )
        # Correction 3: annotate if JS render gap detected
        if is_js_gap:
            evidence += _JS_GAP_NOTE

        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="No structured data found on the page",
            severity="high",
            evidence=evidence,
            action_summary=(
                "Add JSON-LD structured data to your pages. Start with an Organization or WebSite schema. "
                "See skills/structured-data-audit/references/schema_templates.json for ready-to-adapt templates."
            ),
            action_priority="high",
            confidence="manual review recommended" if is_js_gap else "static heuristic",
            cause_tag="entity_identity",
            snippet=snippet,
        ))
        idx[0] += 1
        return findings

    if not schemas and (has_microdata or has_rdfa):
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="Only Microdata/RDFa found — no JSON-LD structured data",
            severity="medium",
            evidence=(
                "Page uses Microdata or RDFa for structured data instead of JSON-LD. "
                "JSON-LD is the recommended format by Google and is easier for AI systems to parse."
            ),
            action_summary=(
                "Migrate existing structured data to JSON-LD format. "
                "JSON-LD is injected in a <script> tag and does not require HTML attribute changes."
            ),
            action_priority="medium",
            confidence="static heuristic",
            cause_tag="entity_identity",
        ))
        idx[0] += 1

    # Per-schema checks
    found_types = set()
    all_same_as = []

    for schema in schemas:
        schema_type = _get_type(schema)
        if not schema_type:
            continue
        found_types.add(schema_type)

        # Check YMYL types
        if schema_type.lower() in ymyl_types:
            findings.append(make_finding(
                skill_prefix=SKILL_PREFIX,
                index=idx[0],
                title=f"YMYL schema type '{schema_type}' used — verify credentials",
                severity="critical",
                evidence=(
                    f"The page declares schema type '{schema_type}' which is a YMYL (Your Money or Your Life) type. "
                    "Using this schema without verified professional credentials may trigger Google manual actions."
                ),
                action_summary=(
                    f"Only use the '{schema_type}' schema type if the site owner holds verified professional credentials. "
                    "Remove it if credentials cannot be verified. Consult a legal or medical professional as appropriate."
                ),
                action_priority="high",
                confidence="static heuristic",
                cause_tag="entity_identity",
            ))
            idx[0] += 1

        # Check required fields
        missing = _check_required_fields(schema, schema_type)
        if missing:
            findings.append(make_finding(
                skill_prefix=SKILL_PREFIX,
                index=idx[0],
                title=f"'{schema_type}' schema missing required fields: {', '.join(missing)}",
                severity="high",
                evidence=(
                    f"The JSON-LD block of type '{schema_type}' is missing the following required fields: "
                    f"{', '.join(missing)}. "
                    "Incomplete schema markup reduces AI understanding of the entity."
                ),
                action_summary=(
                    f"Add the missing fields to your '{schema_type}' JSON-LD: {', '.join(missing)}. "
                    "Reference the template in skills/structured-data-audit/references/schema_templates.json."
                ),
                action_priority="high",
                confidence="static heuristic",
                cause_tag="entity_identity",
            ))
            idx[0] += 1

        # Collect sameAs for checking
        same_as_raw = schema.get("sameAs", [])
        if isinstance(same_as_raw, str):
            same_as_raw = [same_as_raw]
        all_same_as.extend(same_as_raw)

    # sameAs checks (once, across all schemas)
    if all_same_as:
        _check_same_as(all_same_as, findings, idx)
        _check_entity_disambiguation(all_same_as, findings, idx)
    elif schemas:
        # Has schemas but no sameAs at all
        _check_entity_disambiguation([], findings, idx)

    # Correction 3: if a JS render gap was detected, annotate all findings
    # with reduced confidence since some structured data may be client-injected.
    if is_js_gap:
        for f in findings:
            if not f.evidence.endswith(_JS_GAP_NOTE):
                f.evidence += _JS_GAP_NOTE
            if f.confidence == "static heuristic":
                f.confidence = "manual review recommended"

    return findings


def main():
    parser = argparse.ArgumentParser(description="Structured Data Audit")
    parser.add_argument("url", help="Website URL to audit")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    findings = run(args.url)

    if args.json or not sys.stdout.isatty():
        print(json.dumps([f.to_dict() for f in findings], indent=2))
    else:
        print(f"\nStructured Data Audit — {args.url}")
        print(f"Found {len(findings)} finding(s)\n")
        for f in findings:
            print(f"[{f.severity.upper()}] {f.title}")
            print(f"  Evidence: {f.evidence[:120]}...")
            print()


if __name__ == "__main__":
    main()
