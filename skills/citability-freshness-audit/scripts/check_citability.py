"""
skills/citability-freshness-audit/scripts/check_citability.py

Entry point for the citability-freshness-audit skill.

Checks:
  1. Content block quality — answer-like, self-contained, factually dense
  2. Content freshness — datePublished/dateModified age
  3. Author attribution — byline presence
  4. Trust signals — outbound citations
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

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.url_utils import normalise_url, validate_url, get_domain
from shared.html_utils import fetch_and_parse, get_meta_content, get_all_text_blocks
from shared.findings import make_finding, Finding

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
# Zero-width Unicode characters (AI cloaking)
_ZERO_WIDTH_CHARS = {"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"}


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
        ))
        idx[0] += 1


def _check_freshness(soup, findings: list[Finding], idx: list[int]) -> None:
    """Check content freshness via meta dates and structured data."""
    now = datetime.now(timezone.utc)

    # Try structured data dates first
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
                ))
                idx[0] += 1
            return

    if date_str:
        try:
            # Parse various date formats
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
                try:
                    date = datetime.strptime(date_str[:19], fmt[:len(fmt)])
                    if date.tzinfo is None:
                        date = date.replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            else:
                return

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
                ))
                idx[0] += 1
        except Exception:
            pass


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
        soup.find("span", text=re.compile(r"By\s+[A-Z]", re.I)),
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
    ))
    idx[0] += 1


def _check_trust_signals(soup, url: str, findings: list[Finding], idx: list[int]) -> None:
    """Check for outbound citation links as trust signals."""
    domain = get_domain(url)
    outbound_links = [
        a for a in soup.find_all("a", href=True)
        if a["href"].startswith("http") and domain not in a["href"]
    ]
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
        ))
        idx[0] += 1


def _check_cloaking(soup, findings: list[Finding], idx: list[int]) -> None:
    """Detect AI cloaking and prompt injection patterns."""
    signatures = _load_injection_signatures()

    # Check HTML comments for LLM instructions
    for comment in soup.find_all(string=lambda text: isinstance(text, __import__("bs4").Comment)):
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
                    ))
                    idx[0] += 1
                    break

    # Check for zero-width Unicode in visible text
    page_text = soup.get_text()
    found_zw = [c for c in _ZERO_WIDTH_CHARS if c in page_text]
    if found_zw:
        findings.append(make_finding(
            skill_prefix=SKILL_PREFIX,
            index=idx[0],
            title="Zero-width Unicode characters detected in page text",
            severity="critical",
            evidence=(
                f"Found {len(found_zw)} type(s) of zero-width Unicode character(s) embedded in visible text. "
                "These invisible characters are a known AI content manipulation technique and "
                "may trigger AI system content quality filters."
            ),
            action_summary=(
                "Search for and remove zero-width Unicode characters (U+200B, U+200C, U+200D, U+2060, U+FEFF) "
                "from your page content. These may have been introduced by CMS plugins or copy-paste from word processors."
            ),
            action_priority="high",
        ))
        idx[0] += 1

    # Check for CSS-hidden text blocks
    import re as _re
    hidden_elements = soup.find_all(style=_re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", _re.I))
    for el in hidden_elements:
        text = el.get_text(strip=True)
        if len(text.split()) >= 8:
            findings.append(make_finding(
                skill_prefix=SKILL_PREFIX,
                index=idx[0],
                title="CSS-hidden text block detected (potential cloaking)",
                severity="critical",
                evidence=(
                    f"Found a hidden element (display:none or visibility:hidden) containing {len(text.split())} words. "
                    f"Excerpt: '{text[:80]}'. "
                    "Hidden text aimed at AI crawlers is a cloaking technique that violates AI system guidelines."
                ),
                action_summary=(
                    "Review and remove the CSS-hidden text block. "
                    "If the content is legitimate (e.g., a modal or accordion), "
                    "ensure it is not keyword-stuffed and is accessible to screen readers as well."
                ),
                action_priority="high",
            ))
            idx[0] += 1
            break  # One finding for this category is sufficient


def run(url: str) -> list[Finding]:
    """Run the full citability and freshness audit. Returns a list of Finding objects."""
    url = normalise_url(url)
    if not validate_url(url):
        return []

    soup = fetch_and_parse(url)
    if soup is None:
        return []

    findings: list[Finding] = []
    idx = [1]

    _check_content_quality(soup, findings, idx)
    _check_freshness(soup, findings, idx)
    _check_author(soup, findings, idx)
    _check_trust_signals(soup, url, findings, idx)
    _check_cloaking(soup, findings, idx)

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
