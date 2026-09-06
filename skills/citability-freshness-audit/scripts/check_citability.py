"""
skills/citability-freshness-audit/scripts/check_citability.py

Entry point for the citability-freshness-audit skill.

Checks:
  1. Content block quality — answer-like, self-contained, factually dense
  2. Content freshness — datePublished/dateModified age (via dateutil for robustness)
  3. Author attribution — byline presence
  4. Trust signals — outbound citations (root-domain-aware comparison)
  5. AI cloaking / prompt injection detection

Returns a list of Finding objects.

Usage:
    python check_citability.py https://example.com
    python check_citability.py https://example.com --json
"""
from __future__ import annotations

import json
import os
import re
import sys
import argparse
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.url_utils import normalise_url, validate_url, get_domain
from shared.html_utils import fetch_html_and_parse, get_meta_content, get_all_text_blocks
from shared.findings import make_finding, Finding
from shared.js_render_detector import detect_js_render_gap, emit_js_render_finding

# Import dateutil for robust ISO 8601 parsing (handles TZ offsets, Z-suffix, etc.)
try:
    from dateutil import parser as _dateutil_parser
    _HAS_DATEUTIL = True
except ImportError:
    _HAS_DATEUTIL = False

SKILL_PREFIX = "CITE"
_SIG_PATH = os.path.join(os.path.dirname(__file__), "..", "references", "injection_signatures.json")

# Regex patterns for statistical density (numbers, years, percentages)
_STAT_PATTERN = re.compile(r"\b(\d{1,3}(?:,\d{3})*(?:\.\d+)?%?|\$[\d,.]+|\d{4})\b")
# Action-start sentence pattern (answer block quality)
_ANSWER_STARTERS = re.compile(
    r"^(The |A |An |This |These |Our |In |By |With |According |For |When |How |Why |What )",
    re.IGNORECASE,
)
_PROMO_STARTERS = re.compile(
    r"^(We |Our |At |Welcome|Join|Discover|Experience|Transform|Unlock|Revolutionize|Get started)",
    re.IGNORECASE,
)

# Zero-width Unicode characters used for AI cloaking.
# NOTE: \ufeff (UTF-8 BOM) intentionally excluded — it is commonly inserted by
# Windows editors/CMSs and has no cloaking intent. It is checked separately.
_ZERO_WIDTH_CHARS = {"\u200b", "\u200c", "\u200d", "\u2060"}

# UTF-8 BOM — checked separately as a lower-severity encoding signal
_UTF8_BOM = "\ufeff"

# CSS hidden-text patterns that may indicate cloaking (inline style only)
_HIDDEN_CSS_PATTERN = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0"
    r"|font-size\s*:\s*0|height\s*:\s*0",
    re.IGNORECASE,
)

# Elements that legitimately use display:none — skip these to avoid false positives
_SAFE_HIDDEN_TAGS = {"template", "dialog", "details"}
_SAFE_HIDDEN_ROLES = {"dialog", "tooltip", "alertdialog", "menu", "listbox"}


def _load_injection_signatures() -> list[dict]:
    try:
        with open(_SIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("patterns", [])
    except Exception:
        return []


def _score_block(text: str) -> int:
    """Score a single content block 0-100 for AI citability."""
    score = 0
    words = text.split()
    first_sentence = text.split(".")[0] if "." in text else text

    # Answer block quality (30 pts)
    if not _PROMO_STARTERS.match(first_sentence):
        score += 15
    if _ANSWER_STARTERS.match(first_sentence) or len(first_sentence.split()) > 8:
        score += 15

    # Self-containment (25 pts) — penalise anaphoric references
    anaphoric = len(re.findall(r"\b(it|this|these|those|they|them|that)\b", text[:200], re.I))
    score += max(0, 25 - anaphoric * 5)

    # Structural readability (20 pts) — short sentences, no wall of text
    sentences = [s.strip() for s in text.split(".") if s.strip()]
    if sentences:
        avg_len = sum(len(s.split()) for s in sentences) / len(sentences)
        if avg_len <= 20:
            score += 20
        elif avg_len <= 28:
            score += 10

    # Statistical density (15 pts)
    stats = _STAT_PATTERN.findall(text)
    if len(stats) >= 2:
        score += 15
    elif len(stats) == 1:
        score += 8

    # Uniqueness (10 pts) — presence of specific named entities or original claim signals
    if re.search(r"\b(study|research|survey|report|found|according to|data shows)\b", text, re.I):
        score += 10
    elif re.search(r"\b(percent|million|billion|figure|statistic)\b", text, re.I):
        score += 5

    return min(score, 100)


def _check_content_quality(soup, findings: list[Finding], idx: list[int]) -> None:
    """Assess content blocks for AI citability."""
    blocks = get_all_text_blocks(soup, min_words=20)
    if not blocks:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="No substantive content blocks found (≥20 words)",
            severity="medium",
            evidence=(
                "The page has no paragraphs with 20 or more words of text content. "
                "AI systems need substantive text blocks to extract and quote from."
            ),
            action_summary=(
                "Add substantive paragraph content that directly answers user questions. "
                "Each paragraph should ideally start with the answer, then provide supporting detail."
            ),
            action_priority="medium",
            confidence="static heuristic",
            cause_tag="content_quality",
        ))
        idx[0] += 1
        return

    scores = [_score_block(b) for b in blocks]
    avg_score = sum(scores) / len(scores)

    if avg_score < 40:
        low_blocks = [b[:80] for b, s in zip(blocks, scores) if s < 40][:2]
        evidence_examples = " | ".join(low_blocks)
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="Content is poorly structured for AI citation (low citability score)",
            severity="medium",
            evidence=(
                f"Average citability score: {avg_score:.0f}/100 across {len(blocks)} content block(s). "
                f"Low-scoring examples: '{evidence_examples}...'. "
                "Content lacks direct answers, specific facts, and self-contained statements."
            ),
            action_summary=(
                "Rewrite key paragraphs to start with direct answers. Include specific numbers, dates, "
                "and named entities. Each paragraph should make sense if read in isolation by an AI assistant. "
                "Consult skills/citability-freshness-audit/references/citability_rubric.md for guidance."
            ),
            action_priority="medium",
            confidence="static heuristic",
            cause_tag="content_quality",
        ))
        idx[0] += 1


def _parse_date(date_str: str) -> Optional[datetime]:
    """
    Parse a date string using dateutil (preferred) or stdlib fallback.
    Returns a timezone-aware datetime or None if unparseable.
    """
    if _HAS_DATEUTIL:
        try:
            dt = _dateutil_parser.parse(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None
    else:
        # Stdlib fallback — explicit format list without truncation (fix for A13)
        DATE_FORMATS = [
            ("%Y-%m-%dT%H:%M:%S%z",),   # ISO 8601 with TZ offset (+HH:MM)
            ("%Y-%m-%dT%H:%M:%SZ",),     # UTC Z-suffix (non-standard but common)
            ("%Y-%m-%dT%H:%M:%S",),      # No TZ
            ("%Y-%m-%d",),               # Date only
        ]
        # Python <3.7 doesn't support %z with colon — try stripping colon from TZ
        clean = date_str.strip()
        # Normalise Z suffix
        if clean.endswith("Z"):
            clean = clean[:-1] + "+00:00"
        for (fmt,) in DATE_FORMATS:
            try:
                dt = datetime.strptime(clean, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        return None


def _check_freshness(soup, findings: list[Finding], idx: list[int]) -> None:
    """Check content freshness via meta dates and structured data."""
    now = datetime.now(timezone.utc)

    # Try structured data dates first (JSON-LD)
    # NOTE: This works correctly because get_all_text_blocks no longer
    # decompose()s script tags from the shared soup object.
    date_str: Optional[str] = None
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, dict):
                date_str = data.get("dateModified") or data.get("datePublished")
            if date_str:
                break
        except Exception:
            continue

    # Fall back to meta tags
    if not date_str:
        date_str = (
            get_meta_content(soup, "article:modified_time")
            or get_meta_content(soup, "article:published_time")
            or get_meta_content(soup, "date")
        )

    # Fall back to copyright year in visible text
    if not date_str:
        text = soup.get_text()
        match = re.search(r"©\s*(\d{4})", text)
        if match:
            year = int(match.group(1))
            if now.year - year > 1:
                findings.append(make_finding(
                    skill_prefix=SKILL_PREFIX,
                    index=idx[0],
                    title=f"Content may be stale — copyright year is {year}",
                    severity="medium",
                    evidence=(
                        f"The only date signal found is a copyright year of {year}. "
                        "No datePublished, dateModified, or article date meta tags were found. "
                        "AI systems may deprioritise content that appears outdated."
                    ),
                    action_summary=(
                        "Add datePublished and dateModified fields to your JSON-LD structured data. "
                        "Regularly update your content and the dateModified date to signal freshness to AI systems."
                    ),
                    action_priority="medium",
                    confidence="static heuristic",
                    cause_tag="content_freshness",
                ))
                idx[0] += 1
            return

    if date_str:
        date = _parse_date(date_str)
        if date is None:
            return  # Unparseable — skip rather than false-flag

        age_days = (now - date).days
        if age_days > 545:  # ~18 months
            findings.append(make_finding(
                skill_prefix=SKILL_PREFIX,
                index=idx[0],
                title=f"Content is stale — last modified {age_days // 30} months ago",
                severity="high",
                evidence=(
                    f"The page's last modification date is '{date_str}' "
                    f"({age_days} days ago, approximately {age_days // 30} months). "
                    "AI systems deprioritise stale content, especially for time-sensitive topics."
                ),
                action_summary=(
                    "Update the page content and refresh the dateModified field in your JSON-LD. "
                    "Even minor content updates reset the freshness signal for AI systems."
                ),
                action_priority="high",
                confidence="static heuristic",
                cause_tag="content_freshness",
            ))
            idx[0] += 1
    else:
        # No date signal found at all — flag as high (AI prefers dateable content)
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="No content publication date found",
            severity="high",
            evidence=(
                "No datePublished, dateModified, article:published_time, article:modified_time "
                "meta tag, or JSON-LD date field was detected. "
                "AI systems cannot assess content freshness without a publication date signal."
            ),
            action_summary=(
                "Add datePublished and dateModified to your JSON-LD structured data: "
                "\"datePublished\": \"2026-01-15\", \"dateModified\": \"2026-09-01\". "
                "Also add <meta property='article:modified_time' content='...'>."
            ),
            action_priority="high",
            confidence="static heuristic",
            cause_tag="content_freshness",
        ))
        idx[0] += 1


def _check_author(soup, findings: list[Finding], idx: list[int]) -> None:
    """Check for author attribution."""
    # Check meta author
    if get_meta_content(soup, "author"):
        return
    # Check JSON-LD author
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, dict) and data.get("author"):
                return
        except Exception:
            continue
    # Check common byline patterns in HTML
    byline_patterns = [
        soup.find(class_=re.compile(r"author|byline", re.I)),
        soup.find(attrs={"rel": "author"}),
        soup.find("span", string=re.compile(r"By\s+[A-Z]", re.I)),
    ]
    if any(byline_patterns):
        return

    findings.append(make_finding(
        skill_prefix=SKILL_PREFIX,
        index=idx[0],
        title="No author attribution found on the page",
        severity="medium",
        evidence=(
            "No author byline, author meta tag, or JSON-LD author field was detected. "
            "AI systems use author information to assess credibility and E-E-A-T signals."
        ),
        action_summary=(
            "Add author attribution to your pages using: (1) <meta name='author' content='Name'>, "
            "(2) a visible byline element with class 'author' or 'byline', or "
            "(3) an 'author' field in your Article JSON-LD structured data."
        ),
        action_priority="medium",
        confidence="static heuristic",
        cause_tag="trust_signals",
    ))
    idx[0] += 1


def _get_root_domain(netloc: str) -> str:
    """Strip www. prefix and return the root domain for comparison."""
    return netloc.lower().lstrip("www.")


def _check_trust_signals(soup, url: str, findings: list[Finding], idx: list[int]) -> None:
    """
    Check for outbound citation links as trust signals.
    Uses root-domain comparison (strips www.) to avoid false positives with
    subdomains and false negatives with partial-string domain matches (fix A12).
    """
    domain_root = _get_root_domain(get_domain(url))
    outbound_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            continue
        link_netloc = urlparse(href).netloc
        link_root = _get_root_domain(link_netloc)
        if link_root and link_root != domain_root:
            outbound_links.append(a)

    if len(outbound_links) < 2:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="Few or no outbound citation links (low trust signals)",
            severity="medium",
            evidence=(
                f"Found {len(outbound_links)} outbound link(s) to external sources. "
                "AI systems assess trustworthiness partly by whether content cites external sources. "
                "Pages with zero citations appear less authoritative."
            ),
            action_summary=(
                "Add citations to reputable external sources (government databases, academic papers, "
                "industry reports) to support factual claims. "
                "At least 2–3 outbound citations on content pages signals credibility."
            ),
            action_priority="medium",
            confidence="static heuristic",
            cause_tag="trust_signals",
        ))
        idx[0] += 1


def _check_cloaking(soup, findings: list[Finding], idx: list[int]) -> None:
    """Detect AI cloaking and prompt injection patterns."""
    signatures = _load_injection_signatures()

    # Check HTML comments for LLM instructions
    from bs4 import Comment
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        for sig in signatures:
            if sig.get("context") == "html_comment" and sig.get("pattern"):
                if re.search(sig["pattern"], str(comment)):
                    findings.append(make_finding(
                        skill_prefix=SKILL_PREFIX,
                        index=idx[0],
                        title="Potential AI prompt injection in HTML comment",
                        severity="critical",
                        evidence=(
                            f"Pattern '{sig['name']}' detected in an HTML comment. "
                            f"Comment excerpt: '{str(comment)[:100]}'. "
                            "This may be an attempt to manipulate AI system behaviour."
                        ),
                        action_summary=(
                            "Review and remove the flagged HTML comment. "
                            "AI prompt injection attempts are a violation of AI system terms of service "
                            "and may cause your content to be deprioritised or filtered by AI systems."
                        ),
                        action_priority="high",
                        confidence="static heuristic",
                        cause_tag="content_integrity",
                    ))
                    idx[0] += 1
                    break

    # Check for zero-width Unicode in visible text (excludes BOM — see below)
    page_text = soup.get_text()
    found_zw = [c for c in _ZERO_WIDTH_CHARS if c in page_text]
    if found_zw:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="Zero-width Unicode characters detected in page text",
            severity="critical",
            evidence=(
                f"Found {len(found_zw)} type(s) of zero-width Unicode character(s) "
                f"(U+{', U+'.join(f'{ord(c):04X}' for c in found_zw)}) embedded in visible text. "
                "These invisible characters are a known AI content manipulation technique and "
                "may trigger AI system content quality filters."
            ),
            action_summary=(
                "Search for and remove zero-width Unicode characters (U+200B, U+200C, U+200D, U+2060) "
                "from your page content. These may have been introduced by CMS plugins or copy-paste from word processors."
            ),
            action_priority="high",
            confidence="static heuristic",
            cause_tag="content_integrity",
        ))
        idx[0] += 1

    # Check for UTF-8 BOM separately — lower severity, encoding signal not cloaking
    if _UTF8_BOM in page_text:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="UTF-8 BOM detected in page content",
            severity="low",
            evidence=(
                "A UTF-8 Byte Order Mark (U+FEFF) was detected in the page text. "
                "While not a cloaking technique, it indicates legacy encoding practices "
                "that may cause issues with some AI parsing systems."
            ),
            action_summary=(
                "Remove the UTF-8 BOM from your HTML files. "
                "Ensure your CMS or web server serves HTML as UTF-8 without BOM."
            ),
            action_priority="low",
            confidence="static heuristic",
            cause_tag="content_integrity",
        ))
        idx[0] += 1

    # Check for CSS-hidden text blocks (potential cloaking).
    # Threshold raised to 30 words (from 8) to avoid false positives on
    # navigation menus, modals, accordions, and other legitimate UI patterns.
    # Legitimate UI elements (template, dialog, aria-modal) are excluded.
    hidden_elements = soup.find_all(style=_HIDDEN_CSS_PATTERN)
    for el in hidden_elements:
        # Skip known-safe UI patterns
        if el.name in _SAFE_HIDDEN_TAGS:
            continue
        role = el.get("role", "")
        if role in _SAFE_HIDDEN_ROLES:
            continue
        if el.get("aria-modal") == "true":
            continue

        text = el.get_text(strip=True)
        word_count = len(text.split())
        if word_count >= 30:
            findings.append(make_finding(
                skill_prefix=SKILL_PREFIX,
                index=idx[0],
                title="CSS-hidden text block detected (potential cloaking)",
                severity="high",
                evidence=(
                    f"Found a hidden element ({el.name}) with style '{el.get('style', '')[:60]}' "
                    f"containing {word_count} words. "
                    f"Excerpt: '{text[:80]}'. "
                    "Note: this may be a legitimate modal, accordion, or off-canvas element — "
                    "manual review is recommended before taking action."
                ),
                action_summary=(
                    "Review the CSS-hidden text block. "
                    "If the content is legitimate (e.g., a modal or accordion), "
                    "ensure it is not keyword-stuffed and is accessible to screen readers. "
                    "Hidden text aimed specifically at AI crawlers violates AI system guidelines."
                ),
                action_priority="high",
                confidence="static heuristic",
                cause_tag="content_integrity",
            ))
            idx[0] += 1
            break  # One finding per category is sufficient


# Suffix appended to evidence when partial JS render gap is detected.
_PARTIAL_JS_NOTE = " (note: page shows signs of partial client-side rendering — verify manually.)"


def run(url: str) -> list[Finding]:
    """Run the full citability and freshness audit. Returns a list of Finding objects."""
    url = normalise_url(url)
    if not validate_url(url):
        return []

    result = fetch_html_and_parse(url)
    if result is None:
        return []
    html_raw, soup = result

    findings: list[Finding] = []
    idx = [1]

    # Detect JS-render gap once at the top
    js_gap = detect_js_render_gap(html_raw, soup)

    if js_gap and not js_gap.get("partial", False):
        # Full render gap: content_quality and freshness would be false positives
        # on an empty SPA shell — emit the JS-render finding instead and skip them.
        emit_js_render_finding(js_gap, SKILL_PREFIX, findings, idx)
        # Still run non-content checks (author, trust signals, cloaking)
        _check_author(soup, findings, idx)
        _check_trust_signals(soup, url, findings, idx)
        _check_cloaking(soup, findings, idx)
    else:
        if js_gap and js_gap.get("partial", False):
            # Partial render gap: run all checks but tag findings with reduced confidence
            emit_js_render_finding(js_gap, SKILL_PREFIX, findings, idx)

        _check_content_quality(soup, findings, idx)
        _check_freshness(soup, findings, idx)
        _check_author(soup, findings, idx)
        _check_trust_signals(soup, url, findings, idx)
        _check_cloaking(soup, findings, idx)

        # Annotate content-dependent findings with partial-gap note if applicable
        if js_gap and js_gap.get("partial", False):
            for f in findings:
                if f.cause_tag in ("content_quality", "content_freshness"):
                    f.evidence += _PARTIAL_JS_NOTE

    return findings


def main():
    parser = argparse.ArgumentParser(description="Citability & Freshness Audit")
    parser.add_argument("url", help="Website URL to audit")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    findings = run(args.url)

    if args.json or not sys.stdout.isatty():
        print(json.dumps([f.to_dict() for f in findings], indent=2))
    else:
        print(f"\nCitability & Freshness Audit — {args.url}")
        print(f"Found {len(findings)} finding(s)\n")
        for f in findings:
            print(f"[{f.severity.upper()}] {f.title}")
            print(f"  Evidence: {f.evidence[:120]}...")
            print()


if __name__ == "__main__":
    main()
