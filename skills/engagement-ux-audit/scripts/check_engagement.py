"""
skills/engagement-ux-audit/scripts/check_engagement.py

Entry point for the engagement-ux-audit skill.

Checks:
  1. H1 count and structure
  2. Heading hierarchy (no skipped levels)
  3. Meta description clarity
  4. Content scannability (lists/tables)
  5. CTA presence
  6. Navigation element
  7. Mobile viewport meta tag
  8. Image alt text coverage
  9. Open Graph tags (og:title, og:description, og:image)

Returns a list of Finding objects.

Usage:
    python check_engagement.py https://example.com
    python check_engagement.py https://example.com --json
"""
from __future__ import annotations

import json
import os
import re
import sys
import argparse

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.url_utils import normalise_url, validate_url
from shared.html_utils import fetch_html_and_parse, get_meta_content, get_og_property
from shared.findings import make_finding, Finding
from shared.js_render_detector import detect_js_render_gap, emit_js_render_finding

SKILL_PREFIX = "UX"

# Action verbs that indicate a CTA
CTA_VERBS = re.compile(
    r"\b(get|start|download|try|buy|sign up|signup|subscribe|contact|book|schedule|"
    r"learn|read|watch|view|join|register|apply|request|claim|access|explore|discover)\b",
    re.IGNORECASE,
)


def _check_headings(soup, findings: list[Finding], idx: list[int]) -> None:
    """Check H1 presence and heading hierarchy."""
    h1_tags = soup.find_all("h1")

    if len(h1_tags) == 0:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="No <h1> heading found on the page",
            severity="high",
            evidence=(
                "The page has no <h1> element. "
                "AI systems and screen readers rely on H1 as the primary page topic signal. "
                "Missing H1 prevents accurate topic classification."
            ),
            action_summary=(
                "Add exactly one <h1> element that clearly describes the page's primary topic. "
                "The H1 should match or closely relate to the page's <title> tag."
            ),
            action_priority="high",
            confidence="static heuristic",
            cause_tag="onsite_orientation",
        ))
        idx[0] += 1

    elif len(h1_tags) > 1:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title=f"Multiple <h1> tags found ({len(h1_tags)})",
            severity="high",
            evidence=(
                f"The page contains {len(h1_tags)} <h1> elements: "
                f"{', '.join([repr(h.get_text(strip=True)[:40]) for h in h1_tags[:3]])}. "
                "Multiple H1s confuse AI systems about the page's primary topic."
            ),
            action_summary=(
                "Reduce to exactly one <h1> per page. "
                "Use <h2> for section headings. "
                "If using a CMS, check theme templates for duplicate H1 rendering."
            ),
            action_priority="high",
            confidence="static heuristic",
            cause_tag="onsite_orientation",
        ))
        idx[0] += 1

    # Check heading hierarchy (no skipped levels)
    all_headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    heading_levels = [int(h.name[1]) for h in all_headings]
    for i in range(1, len(heading_levels)):
        prev = heading_levels[i - 1]
        curr = heading_levels[i]
        if curr > prev + 1:
            findings.append(make_finding(
                skill_prefix=SKILL_PREFIX,
                index=idx[0],
                title=f"Heading level skipped: h{prev} → h{curr}",
                severity="medium",
                evidence=(
                    f"The page jumps from <h{prev}> directly to <h{curr}> without an intermediate level. "
                    "Skipped heading levels break document outline structure and "
                    "reduce content parsability for AI systems."
                ),
                action_summary=(
                    f"Add an <h{prev + 1}> between your <h{prev}> and <h{curr}> headings, "
                    "or change the <h{curr}> to <h{prev + 1}>. "
                    "Heading levels should increment by one at a time."
                ),
                action_priority="medium",
                confidence="static heuristic",
                cause_tag="onsite_orientation",
            ))
            idx[0] += 1
            break  # One hierarchy finding is enough


def _check_meta_description(soup, findings: list[Finding], idx: list[int]) -> None:
    """Check meta description presence and quality."""
    description = get_meta_content(soup, "description")
    if not description:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="Meta description is missing",
            severity="medium",
            evidence=(
                "No <meta name='description'> tag was found. "
                "AI systems and search engines use meta descriptions to summarise page content "
                "in search results and AI-generated answers."
            ),
            action_summary=(
                "Add a meta description tag: <meta name='description' content='...'> "
                "with a concise (50–160 characters), factual summary of the page's primary value. "
                "Avoid marketing language; prefer specific, factual statements."
            ),
            action_priority="medium",
            confidence="static heuristic",
            cause_tag="onsite_orientation",
        ))
        idx[0] += 1
    elif len(description) < 50:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title=f"Meta description is too short ({len(description)} chars)",
            severity="medium",
            evidence=(
                f"Meta description: '{description}'. "
                f"At {len(description)} characters, this is too short to be informative for AI systems. "
                "Optimal range is 50–160 characters."
            ),
            action_summary=(
                "Expand the meta description to 50–160 characters. "
                "Include specific facts, key offerings, and what makes the page uniquely valuable."
            ),
            action_priority="medium",
            confidence="static heuristic",
            cause_tag="onsite_orientation",
        ))
        idx[0] += 1


def _check_scannability(soup, findings: list[Finding], idx: list[int]) -> None:
    """Check content scannability — lists and tables."""
    paragraphs = soup.find_all("p")
    word_count = sum(len(p.get_text().split()) for p in paragraphs)

    has_list = bool(soup.find(["ul", "ol"]))
    has_table = bool(soup.find("table"))

    if word_count > 400 and not has_list and not has_table:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="Long page content lacks lists or tables (poor scannability)",
            severity="medium",
            evidence=(
                f"The page contains approximately {word_count} words in paragraph text "
                "but no <ul>, <ol>, or <table> elements. "
                "Dense walls of text are harder for AI systems to extract structured information from."
            ),
            action_summary=(
                "Break up long prose content with bulleted lists, numbered steps, or comparison tables. "
                "Lists and tables are particularly well-parsed by AI systems and improve citation quality."
            ),
            action_priority="medium",
            confidence="static heuristic",
            cause_tag="content_quality",
        ))
        idx[0] += 1


def _check_cta(soup, findings: list[Finding], idx: list[int]) -> None:
    """
    Check for the presence of a clear Call to Action.

    Heuristic improvements (fix A11):
    - Excludes CTAs found only inside <footer> — footer nav links with action
      verbs ("View cart", "Read terms") are not page-level CTAs.
    - Requires minimum 2 words in CTA text to avoid single-word false positives.
    - A <form> outside the footer still counts as a valid CTA signal.
    """
    footer = soup.find("footer")

    def _is_in_footer(el) -> bool:
        """Return True if el is a descendant of the footer."""
        return footer is not None and footer in el.parents

    def _is_valid_cta(el) -> bool:
        """True if element has an action verb and at least 2 words of text."""
        text = el.get_text(strip=True)
        words = text.split()
        return len(words) >= 2 and CTA_VERBS.search(text) is not None

    # Check links and buttons outside footer
    cta_elements = soup.find_all(["a", "button"])
    has_cta = any(
        _is_valid_cta(el) and not _is_in_footer(el)
        for el in cta_elements
    )

    # Check for a form outside the footer (contact form, signup form, etc.)
    if not has_cta:
        forms = soup.find_all("form")
        has_cta = any(not _is_in_footer(f) for f in forms)

    if not has_cta:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="No clear Call to Action (CTA) detected on the page",
            severity="high",
            evidence=(
                "No <a>, <button>, or <form> element with a 2+ word action verb (Get Started, "
                "Sign Up, Contact Us, Book a Demo, etc.) was found outside the page footer. "
                "Visitors arriving from AI referrals need a clear next step."
            ),
            action_summary=(
                "Add a prominent CTA element with a clear action phrase in the page body or header. "
                "Example: <a href='/contact'>Get in Touch</a> or <button>Start Free Trial</button>. "
                "CTAs in the footer alone are insufficient — place them above the fold."
            ),
            action_priority="high",
            confidence="static heuristic",
            cause_tag="onsite_orientation",
        ))
        idx[0] += 1


def _check_navigation(soup, findings: list[Finding], idx: list[int]) -> None:
    """Check for a navigation element."""
    has_nav = bool(soup.find("nav"))
    if not has_nav:
        # Fallback: check for a header with multiple links
        header = soup.find("header")
        has_nav = header and len(header.find_all("a")) >= 3

    if not has_nav:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="No navigation element found",
            severity="high",
            evidence=(
                "No <nav> element was detected. "
                "Visitors referred by AI assistants arrive on a specific page and need clear navigation "
                "to explore the site further."
            ),
            action_summary=(
                "Add a <nav> element with links to key site sections. "
                "Ensure navigation is visible at the top of the page and accessible on mobile."
            ),
            action_priority="high",
            confidence="static heuristic",
            cause_tag="onsite_orientation",
        ))
        idx[0] += 1


def _check_viewport(soup, findings: list[Finding], idx: list[int]) -> None:
    """Check for mobile viewport meta tag."""
    viewport = get_meta_content(soup, "viewport")
    if not viewport:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="Mobile viewport meta tag is missing",
            severity="high",
            evidence=(
                "No <meta name='viewport'> tag was found. "
                "Without this tag, the page will not render correctly on mobile devices. "
                "AI referral traffic increasingly comes from mobile users."
            ),
            action_summary=(
                "Add to your <head>: "
                "<meta name='viewport' content='width=device-width, initial-scale=1'>."
            ),
            action_priority="high",
            confidence="static heuristic",
            cause_tag="onsite_orientation",
        ))
        idx[0] += 1


def _check_image_alt(soup, findings: list[Finding], idx: list[int]) -> None:
    """Check image alt text coverage."""
    images = soup.find_all("img")
    if not images:
        return

    # Exclude decorative images (empty alt is acceptable for decorative)
    informational = [img for img in images if img.get("src") and not img.get("role") == "presentation"]
    missing_alt = [img for img in informational if not img.get("alt", "").strip()]
    pct_missing = (len(missing_alt) / len(informational) * 100) if informational else 0

    if pct_missing > 20:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title=f"{int(pct_missing)}% of images are missing alt text",
            severity="medium",
            evidence=(
                f"{len(missing_alt)} of {len(informational)} images lack alt text. "
                "AI systems cannot understand image content without alt text, "
                "reducing overall page comprehension quality."
            ),
            action_summary=(
                "Add descriptive alt text to all informational images. "
                "For decorative images, use alt='' (empty string). "
                "Alt text should describe what the image shows, not just 'image' or the filename."
            ),
            action_priority="medium",
            confidence="static heuristic",
            cause_tag="content_quality",
        ))
        idx[0] += 1


def _check_open_graph(soup, findings: list[Finding], idx: list[int]) -> None:
    """Check Open Graph tag completeness."""
    og_title = get_og_property(soup, "og:title")
    og_description = get_og_property(soup, "og:description")
    og_image = get_og_property(soup, "og:image")

    if not og_title:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="Open Graph title (og:title) is missing",
            severity="medium",
            evidence=(
                "No <meta property='og:title'> tag found. "
                "AI chatbots and social platforms use og:title to display page previews."
            ),
            action_summary=(
                "Add <meta property='og:title' content='Page Title'> to your <head>. "
                "Use the same value as your <title> tag."
            ),
            action_priority="medium",
            confidence="static heuristic",
            cause_tag="onsite_orientation",
        ))
        idx[0] += 1

    if not og_description:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="Open Graph description (og:description) is missing",
            severity="medium",
            evidence=(
                "No <meta property='og:description'> tag found. "
                "AI chatbots and social platforms use og:description to summarise pages in previews."
            ),
            action_summary=(
                "Add <meta property='og:description' content='...'> matching your meta description."
            ),
            action_priority="medium",
            confidence="static heuristic",
            cause_tag="onsite_orientation",
        ))
        idx[0] += 1

    if not og_image:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="Open Graph image (og:image) is missing",
            severity="low",
            evidence=(
                "No <meta property='og:image'> tag found. "
                "Pages without og:image appear as text-only previews in social and AI chat surfaces."
            ),
            action_summary=(
                "Add <meta property='og:image' content='https://yourdomain.com/og-image.jpg'>. "
                "Use an image at least 1200×630 pixels for best display across platforms."
            ),
            action_priority="low",
            confidence="static heuristic",
            cause_tag="onsite_orientation",
        ))
        idx[0] += 1


def run(url: str) -> list[Finding]:
    """Run the full engagement UX audit. Returns a list of Finding objects."""
    url = normalise_url(url)
    if not validate_url(url):
        return []

    from shared.html_utils import fetch_html_and_parse as _fhap
    result = _fhap(url)
    if result is None:
        return []
    html_raw, soup = result

    findings: list[Finding] = []
    idx = [1]

    # Detect JS-render gap first — if detected, annotate content-dependent findings
    js_gap = detect_js_render_gap(html_raw, soup)
    if js_gap:
        emit_js_render_finding(js_gap, SKILL_PREFIX, findings, idx)

    _check_headings(soup, findings, idx)
    _check_meta_description(soup, findings, idx)
    _check_scannability(soup, findings, idx)
    _check_cta(soup, findings, idx)
    _check_navigation(soup, findings, idx)
    _check_viewport(soup, findings, idx)
    _check_image_alt(soup, findings, idx)
    _check_open_graph(soup, findings, idx)

    return findings


def main():
    parser = argparse.ArgumentParser(description="Engagement & UX Audit")
    parser.add_argument("url", help="Website URL to audit")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    findings = run(args.url)

    if args.json or not sys.stdout.isatty():
        print(json.dumps([f.to_dict() for f in findings], indent=2))
    else:
        print(f"\nEngagement & UX Audit — {args.url}")
        print(f"Found {len(findings)} finding(s)\n")
        for f in findings:
            print(f"[{f.severity.upper()}] {f.title}")
            print(f"  Evidence: {f.evidence[:120]}...")
            print()


if __name__ == "__main__":
    main()
