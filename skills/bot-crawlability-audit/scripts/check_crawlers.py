"""
skills/bot-crawlability-audit/scripts/check_crawlers.py

Entry point for the bot-crawlability-audit skill.

Checks:
  1. robots.txt reachability and AI bot rules
  2. Live HTTP probe for priority AI crawlers (declared-vs-actual mismatch)
     — only probes bots that robots.txt declares as Allowed (brief mandate)
  3. /llms.txt and /llms-full.txt presence
  4. /sitemap.xml presence (also checks robots.txt Sitemap directive)
  5. WAF/CDN detection on bot-blocked responses

Returns a list of Finding objects (or dicts when run standalone).

Usage:
    python check_crawlers.py https://example.com
    python check_crawlers.py https://example.com --json
"""
from __future__ import annotations

import json
import os
import re
import sys
import argparse

# Allow running as a standalone script from any directory
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.url_utils import normalise_url, validate_url, base_url, llms_txt_url, llms_full_txt_url, sitemap_url
from shared.http_client import get, head
from shared.findings import make_finding, Finding

# Load sibling modules using importlib (directory name contains hyphens)
import importlib.util as _ilu


def _load_local(module_name, filename):
    _path = os.path.join(os.path.dirname(__file__), filename)
    _spec = _ilu.spec_from_file_location(module_name, _path)
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod


_robots = _load_local("robots_parser", "robots_parser.py")
fetch_robots_txt = _robots.fetch_robots_txt
parse_robots = _robots.parse_robots
is_bot_allowed = _robots.is_bot_allowed

_waf = _load_local("waf_detector", "waf_detector.py")
detect_waf = _waf.detect_waf


# Module prefix for finding IDs
SKILL_PREFIX = "CRAWL"

# Priority bots to probe live (subset — probing all 22 would be slow).
# Uses realistic full User-Agent strings to accurately trigger WAF rules (fix A9).
PRIORITY_BOTS = [
    {
        "name": "GPTBot",
        "ua_full": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.1; +https://openai.com/gptbot)",
        "ua_token": "GPTBot",
    },
    {
        "name": "ClaudeBot",
        "ua_full": "Mozilla/5.0 (compatible; ClaudeBot/1.0; +https://anthropic.com/claude)",
        "ua_token": "ClaudeBot",
    },
    {
        "name": "PerplexityBot",
        "ua_full": "Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
        "ua_token": "PerplexityBot",
    },
    {
        "name": "OAI-SearchBot",
        "ua_full": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)",
        "ua_token": "OAI-SearchBot",
    },
    {
        "name": "Googlebot",
        "ua_full": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "ua_token": "Googlebot",
    },
]

# Load full bot registry from references
_UA_REGISTRY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "references", "ai_user_agents.json"
)


def _load_all_bots() -> list[dict]:
    """Load all AI bot User-Agents from the registry."""
    try:
        with open(_UA_REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        bots = []
        for cat in data.get("categories", {}).values():
            bots.extend(cat.get("bots", []))
        return bots
    except Exception:
        return [{"name": b["name"], "user_agent": b["ua_token"]} for b in PRIORITY_BOTS]


def _check_robots(url: str, findings: list[Finding], idx: list[int]) -> tuple:
    """
    Fetch and parse robots.txt.
    Returns (robots_accessible: bool, robots_parser_or_None, blocked_bots: list[str],
             raw_robots_text: str | None)
    """
    burl = base_url(url)
    raw = fetch_robots_txt(burl)

    if raw is None:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="robots.txt is not accessible",
            severity="medium",
            evidence=f"HTTP request to {burl}/robots.txt returned no response or a non-200 status code.",
            action_summary=(
                "Create a /robots.txt file at your domain root. "
                "Even an empty one signals good bot citizenship and allows AI crawlers to discover your crawl rules."
            ),
            action_priority="medium",
            confidence="robots.txt parse",
            cause_tag="crawler_access",
        ))
        idx[0] += 1
        return False, None, [], None

    parser = parse_robots(raw, burl)
    all_bots = _load_all_bots()

    blocked_bots = []
    for bot in all_bots:
        ua = bot.get("user_agent", "")
        if ua and not is_bot_allowed(parser, ua, "/"):
            blocked_bots.append(bot["name"])

    if blocked_bots:
        names = ", ".join(blocked_bots[:5])
        more = f" (and {len(blocked_bots)-5} more)" if len(blocked_bots) > 5 else ""
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title=f"robots.txt blocks {len(blocked_bots)} AI crawler(s)",
            severity="high",
            evidence=(
                f"The following AI crawlers are disallowed in robots.txt: {names}{more}. "
                f"This prevents these systems from indexing or citing your content."
            ),
            action_summary=(
                "Review your robots.txt Disallow rules. Remove or narrow rules that block AI crawlers "
                "(GPTBot, ClaudeBot, PerplexityBot) unless you have a specific legal reason to exclude them. "
                "Use per-bot Disallow directives to allow retrieval bots while still blocking training bots if desired."
            ),
            action_priority="high",
            confidence="robots.txt parse",
            cause_tag="crawler_access",
        ))
        idx[0] += 1

    return True, parser, blocked_bots, raw


def _check_live_probes(url: str, parser, findings: list[Finding], idx: list[int]) -> None:
    """
    Perform live HTTP probes using AI bot User-Agents.
    Detect declared-vs-actual mismatches (robots.txt allows, but live returns 403/401/429).

    COMPLIANCE: Per the audit brief, robots.txt MUST be respected.
    We only probe bots that robots.txt declares as Allowed (or unconstrained).
    Disallowed bots are skipped — their status is already captured as a "high" finding
    by _check_robots(). This prevents the auditor from sending HTTP requests
    that the site has explicitly forbidden via robots.txt.
    """
    for bot in PRIORITY_BOTS:
        ua_full = bot["ua_full"]
        ua_token = bot["ua_token"]
        bot_name = bot["name"]

        # Use bare token for robots.txt matching (robots.txt token-matches UA)
        declared_allowed = is_bot_allowed(parser, ua_token, "/") if parser else True

        # COMPLIANCE: Do not probe bots that robots.txt has explicitly disallowed
        if not declared_allowed:
            continue

        resp = get(url, user_agent=ua_full)
        if resp is None:
            continue  # Network failure — skip this bot

        actual_code = resp.status_code
        blocking_codes = {403, 401, 429}

        if actual_code in blocking_codes:
            # CRITICAL: Declared-vs-Actual mismatch
            waf = detect_waf(resp)
            waf_note = f" {waf} WAF/CDN detected in response headers." if waf else ""

            findings.append(make_finding(
                skill_prefix=SKILL_PREFIX,
                index=idx[0],
                title=f"{bot_name} blocked by server despite robots.txt Allow",
                severity="critical",
                evidence=(
                    f"robots.txt declares Allow: / for {bot_name} (token: {ua_token}). "
                    f"Live HTTP GET returned HTTP {actual_code}.{waf_note} "
                    f"This means the crawler is silently blocked at the server/WAF layer."
                ),
                action_summary=(
                    f"Check your WAF, CDN, or server firewall rules for rules that block the "
                    f"'{ua_token}' User-Agent string.{' Open the ' + waf + ' dashboard and review bot management rules.' if waf else ''} "
                    f"Test with: curl -A '{ua_full}' {url}"
                ),
                action_priority="high",
                confidence="live HTTP probe",
                cause_tag="crawler_access",
            ))
            idx[0] += 1

        elif actual_code == 402:
            findings.append(make_finding(
                skill_prefix=SKILL_PREFIX,
                index=idx[0],
                title=f"{bot_name} encounters HTTP 402 (pay-per-crawl) gate",
                severity="medium",
                evidence=(
                    f"Live HTTP GET with User-Agent '{ua_token}' returned HTTP 402 Payment Required. "
                    f"This is a pay-per-crawl gate, not a block, but may limit AI indexing."
                ),
                action_summary=(
                    "Consider whether the pay-per-crawl model aligns with your AI discoverability goals. "
                    "If you want AI systems to freely index your content, remove the 402 gate for AI retrieval bots."
                ),
                action_priority="medium",
                confidence="live HTTP probe",
                cause_tag="crawler_access",
            ))
            idx[0] += 1


def _check_llms_txt(url: str, findings: list[Finding], idx: list[int]) -> None:
    """Check for /llms.txt and /llms-full.txt presence."""
    llms_url = llms_txt_url(url)
    resp = head(llms_url)
    if resp is None or resp.status_code not in (200, 301, 302):
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="/llms.txt file not found",
            severity="medium",
            evidence=(
                f"HTTP HEAD request to {llms_url} returned "
                f"status {resp.status_code if resp else 'no response'}. "
                "The llms.txt standard allows site owners to declare AI-readable content "
                "and usage policies in a machine-readable format."
            ),
            action_summary=(
                "Create an /llms.txt file at your domain root following the llms.txt specification. "
                "This signals to AI systems what content they may use and how. "
                "See https://llmstxt.org for the format specification."
            ),
            action_priority="medium",
            confidence="static heuristic",
            cause_tag="crawler_access",
        ))
        idx[0] += 1


def _check_sitemap(url: str, raw_robots: "str | None", findings: list[Finding], idx: list[int]) -> None:
    """
    Check for /sitemap.xml presence.
    Also checks the robots.txt Sitemap: directive as a fallback — many sites
    declare sitemaps at non-standard paths via this directive.
    """
    # First: check robots.txt Sitemap: directive (most accurate signal)
    if raw_robots:
        sitemap_match = re.search(r"(?im)^Sitemap:\s*(\S+)", raw_robots)
        if sitemap_match:
            declared_sitemap = sitemap_match.group(1).strip()
            resp = head(declared_sitemap)
            if resp and resp.status_code in (200, 301, 302):
                return  # Sitemap found and reachable via robots.txt directive
            # Declared but unreachable
            findings.append(make_finding(
                skill_prefix=SKILL_PREFIX,
                index=idx[0],
                title="Sitemap declared in robots.txt is unreachable",
                severity="medium",
                evidence=(
                    f"robots.txt declares Sitemap: {declared_sitemap} "
                    f"but HEAD request returned {resp.status_code if resp else 'no response'}. "
                    "AI crawlers follow the Sitemap directive to discover all pages."
                ),
                action_summary=(
                    f"Fix or update the Sitemap URL in robots.txt: {declared_sitemap}. "
                    "Verify the sitemap is publicly accessible at the declared URL."
                ),
                action_priority="medium",
                confidence="live HTTP probe",
                cause_tag="crawler_access",
            ))
            idx[0] += 1
            return

    # Fall back to canonical /sitemap.xml path
    smap_url = sitemap_url(url)
    resp = head(smap_url)
    if resp is None or resp.status_code not in (200, 301, 302):
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="/sitemap.xml not found",
            severity="medium",
            evidence=(
                f"HTTP HEAD request to {smap_url} returned "
                f"status {resp.status_code if resp else 'no response'}. "
                "No Sitemap directive was found in robots.txt either. "
                "A sitemap helps AI search crawlers discover all pages on your site."
            ),
            action_summary=(
                "Generate and publish an XML sitemap at /sitemap.xml. "
                "Most CMS platforms (WordPress, Shopify, etc.) can generate this automatically. "
                "Also reference it in your robots.txt: Sitemap: https://yourdomain.com/sitemap.xml"
            ),
            action_priority="medium",
            confidence="static heuristic",
            cause_tag="crawler_access",
        ))
        idx[0] += 1


def run(url: str) -> list[Finding]:
    """
    Run the full bot-crawlability audit.
    Returns a list of Finding objects.
    """
    url = normalise_url(url)
    if not validate_url(url):
        return []

    findings: list[Finding] = []
    idx = [1]  # Mutable index for sequential finding IDs

    robots_ok, parser, _, raw_robots = _check_robots(url, findings, idx)
    if robots_ok:
        _check_live_probes(url, parser, findings, idx)
    _check_llms_txt(url, findings, idx)
    _check_sitemap(url, raw_robots, findings, idx)

    return findings


def main():
    parser = argparse.ArgumentParser(description="Bot Crawlability Audit")
    parser.add_argument("url", help="Website URL to audit")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    findings = run(args.url)

    if args.json or not sys.stdout.isatty():
        print(json.dumps([f.to_dict() for f in findings], indent=2))
    else:
        print(f"\nBot Crawlability Audit — {args.url}")
        print(f"Found {len(findings)} finding(s)\n")
        for f in findings:
            print(f"[{f.severity.upper()}] {f.title}")
            print(f"  Evidence: {f.evidence[:120]}...")
            print()


if __name__ == "__main__":
    main()
