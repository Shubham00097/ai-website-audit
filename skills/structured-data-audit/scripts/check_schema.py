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
from bs4 import BeautifulSoup

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.url_utils import normalise_url, validate_url
from shared.html_utils import fetch_html_and_parse
from shared.http_client import get, head
from shared.findings import make_finding as _make_finding_base, Finding


def make_finding(*args, **kwargs):
    """Mark every schema result as dependent on the page's static HTML."""
    kwargs.setdefault("content_dependent", True)
    return _make_finding_base(*args, **kwargs)

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


def _corroboration_candidates(same_as: list[str]) -> list[str]:
    """Choose up to two sources, favouring pages with cheap public markup."""
    unique_links = [link for link in dict.fromkeys(same_as) if link.startswith("http")]
    preferred = [
        link for link in unique_links
        if "wikidata.org" in link.lower() or "wikipedia.org" in link.lower()
    ]
    return (preferred + [link for link in unique_links if link not in preferred])[:2]


def _check_same_as(
    same_as: list[str], findings: list[Finding], idx: list[int]
) -> dict[str, object]:
    """Check sameAs links and return live GET responses for corroboration.

    A selected corroboration candidate is fetched once with GET, which both
    establishes liveness and supplies its HTML. Other sameAs links use HEAD,
    retaining the existing inexpensive liveness check without duplicate
    requests to a candidate source.
    """
    unique_links = list(dict.fromkeys(same_as))[:6]
    candidates = set(_corroboration_candidates(unique_links))
    corroboration_responses: dict[str, object] = {}
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

        resp = get(link) if link in candidates else head(link)
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
        elif link in candidates:
            corroboration_responses[link] = resp

    return corroboration_responses


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


def _normalise_fact(value: object) -> str:
    """Normalise lightly so harmless punctuation/case changes do not mismatch."""
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _fact_matches(left: str, right: str) -> bool:
    """Use exact/containment comparison for short, human-readable facts."""
    normal_left = _normalise_fact(left)
    normal_right = _normalise_fact(right)
    return bool(normal_left and normal_right and (
        normal_left == normal_right
        or normal_left in normal_right
        or normal_right in normal_left
    ))


def _date_fact(value: object) -> str:
    if not isinstance(value, str):
        return ""
    match = re.search(r"\b(\d{4})(?:-\d{2}-\d{2})?\b", value)
    return match.group(1) if match else ""


def _own_entity_facts(schemas: list[dict], soup) -> dict[str, str]:
    """Extract organisation/entity facts declared by the audited page."""
    for schema in schemas:
        name = schema.get("name") or schema.get("legalName")
        if not isinstance(name, str) or not name.strip():
            continue
        address = schema.get("address") or schema.get("location")
        if isinstance(address, dict):
            location = (
                address.get("addressLocality") or address.get("addressRegion")
                or address.get("addressCountry") or address.get("name") or ""
            )
        else:
            location = address if isinstance(address, str) else ""
        return {
            "name": name.strip(),
            "founding_date": _date_fact(schema.get("foundingDate") or schema.get("foundingDate")),
            "location": str(location).strip(),
        }

    heading = soup.find("h1")
    if heading and heading.get_text(strip=True):
        return {"name": heading.get_text(strip=True), "founding_date": "", "location": ""}
    return {}


def _external_entity_facts(response) -> dict[str, str]:
    """Extract a small comparable fact set from common Wiki/infobox markup."""
    try:
        external_soup = BeautifulSoup(response.text, "html.parser")
    except Exception:
        return {}

    name_tag = external_soup.select_one("#firstHeading, .wikibase-title-label, h1, title")
    facts = {"name": name_tag.get_text(" ", strip=True) if name_tag else ""}
    labels = {
        "founding_date": ("founded", "inception", "established", "formed"),
        "location": ("headquarters", "location", "head office", "country"),
    }
    for row in external_soup.select("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        label = cells[0].get_text(" ", strip=True).lower()
        value = cells[1].get_text(" ", strip=True)
        for fact_name, names in labels.items():
            if any(candidate in label for candidate in names) and not facts.get(fact_name):
                facts[fact_name] = _date_fact(value) if fact_name == "founding_date" else value
    return {key: value for key, value in facts.items() if value}


def _check_corroboration(
    source_responses: dict[str, object],
    schemas: list[dict],
    soup,
    findings: list[Finding],
    idx: list[int],
) -> None:
    """Flag contradictory entity facts found in one independent live source."""
    own_facts = _own_entity_facts(schemas, soup)
    if not own_facts:
        return

    for source, response in source_responses.items():
        external_facts = _external_entity_facts(response)
        comparisons = []
        for label in ("name", "founding_date", "location"):
            own_value = own_facts.get(label, "")
            external_value = external_facts.get(label, "")
            if own_value and external_value and not _fact_matches(own_value, external_value):
                comparisons.append((label.replace("_", " "), own_value, external_value))

        if comparisons:
            quoted = "; ".join(
                f"{label}: page says '{own}', source says '{external}'"
                for label, own, external in comparisons
            )
            findings.append(make_finding(
                skill_prefix=SKILL_PREFIX,
                index=idx[0],
                title="Entity facts disagree across sources",
                severity="high",
                evidence=(
                    f"Independent source {source} conflicts with the page's declared entity facts: {quoted}. "
                    "Conflicting identity information can reduce AI systems' confidence in the entity."
                ),
                action_summary=(
                    "Verify the organisation name, founding date, and location in both your JSON-LD and "
                    "the linked independent profile. Correct the stale source or update sameAs to the "
                    "authoritative profile before publishing consistent facts everywhere."
                ),
                action_priority="high",
                confidence="live HTTP probe",
                cause_tag="trust_signals",
            ))
            idx[0] += 1
            return


def _check_verifiable_presence(
    same_as: list[str], findings: list[Finding], idx: list[int]
) -> None:
    """Report an absent identity footprint only when no external source was declared."""
    if same_as:
        return
    findings.append(make_finding(
        skill_prefix=SKILL_PREFIX,
        index=idx[0],
        title="No independently verifiable presence found for this entity",
        severity="medium",
        evidence=(
            "No sameAs or other external identity source was declared in this page's JSON-LD. "
            "AI systems have no linked independent profile to corroborate the entity's identity."
        ),
        action_summary=(
            "Create or verify authoritative external profiles (preferably Wikidata, LinkedIn, or Crunchbase) "
            "and link them from your Organization JSON-LD using sameAs."
        ),
        action_priority="medium",
        confidence="static heuristic",
        cause_tag="trust_signals",
    ))
    idx[0] += 1


_TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "..", "references", "schema_templates.json")

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
            confidence="static heuristic",
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
        source_responses = _check_same_as(all_same_as, findings, idx)
        _check_entity_disambiguation(all_same_as, findings, idx)
        _check_corroboration(source_responses, schemas, soup, findings, idx)
    elif schemas:
        # Has schemas but no sameAs at all
        _check_entity_disambiguation([], findings, idx)
        _check_verifiable_presence([], findings, idx)

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
