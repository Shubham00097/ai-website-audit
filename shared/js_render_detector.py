"""
shared/js_render_detector.py

Static JS-render gap detection using only the raw HTML already fetched.
Zero additional HTTP requests. No headless browser required.

The detector identifies pages where visible content is assembled by JavaScript
at runtime (SPAs, client-side hydrated frameworks) and a plain HTTP GET therefore
returns a near-empty shell. Because the auditor uses requests + BeautifulSoup
(no JS execution), content-dependent findings on such pages would be false positives.

Detection heuristics (all static, no network):
  1. Framework marker strings in raw HTML (data-reactroot, __NEXT_DATA__, etc.)
  2. Body text word count vs. external script count ratio
  3. <noscript> fallback content quality

Usage:
    from shared.js_render_detector import detect_js_render_gap, emit_js_render_finding
    js_gap = detect_js_render_gap(html_raw, soup)
    if js_gap:
        emit_js_render_finding(js_gap, SKILL_PREFIX, findings, idx)
"""
from __future__ import annotations

from typing import Optional
from bs4 import BeautifulSoup
from shared.findings import make_finding, Finding

# Framework markers present in raw HTML source (not in rendered DOM)
# Format: (marker_string, framework_name)
JS_FRAMEWORK_MARKERS = [
    ("__NEXT_DATA__",       "Next.js"),          # Next.js hydration data in <script>
    ("data-reactroot",      "React"),             # React 16 root marker
    ("data-react-helmet",   "React"),             # React Helmet SSR
    ("__nuxt__",            "Nuxt.js"),           # Nuxt.js hydration
    ("id=\"__nuxt\"",       "Nuxt.js"),           # Nuxt.js app root
    ("ng-version=",         "Angular"),           # Angular version attribute
    ("data-vue-app",        "Vue 3"),             # Vue 3 app root
    ("data-server-rendered","Vue SSR"),           # Vue SSR marker
    ("data-svelte-h",       "Svelte"),            # Svelte hydration marker
    ("__sveltekit_",        "SvelteKit"),         # SvelteKit
    ("x-data=",             "Alpine.js"),         # Alpine.js reactive component
    ("ember-application",   "Ember.js"),          # Ember.js app root
    ("data-gatsby-head",    "Gatsby"),            # Gatsby head component
    ("window.__REMIX_",     "Remix"),             # Remix SSR data
    ("window.REMIX_DEV_",   "Remix"),             # Remix dev overlay
]

# Thresholds for render-gap classification
_EMPTY_BODY_WORD_THRESHOLD = 80    # < 80 words = strong render-gap signal
_THIN_BODY_WORD_THRESHOLD = 300    # 80-300 words = possible partial SSR
_SCRIPT_COUNT_THRESHOLD = 3        # > 3 external scripts with thin body = suspicious


def detect_js_render_gap(html: str, soup: BeautifulSoup) -> Optional[dict]:
    """
    Detect whether the page relies on JavaScript rendering.

    Returns a dict describing the gap if detected, or None if the page
    appears to be server-rendered with sufficient static content.

    Return dict keys:
        framework (str | None): detected JS framework name
        body_text_words (int): word count of visible body text
        script_count (int): number of external <script src="..."> tags
        partial (bool): True if partial SSR (content present but likely incomplete)
        evidence (str): human-readable explanation for findings
    """
    # Step 1: Detect framework markers in raw HTML
    detected_framework: Optional[str] = None
    for marker, name in JS_FRAMEWORK_MARKERS:
        if marker in html:
            detected_framework = name
            break

    # Step 2: Measure body text word count (excludes scripts, noscript, head)
    body = soup.find("body")
    if not body:
        return None

    # Get body text without script/style/noscript content
    body_clone_text = " ".join(
        el.get_text(separator=" ", strip=True)
        for el in body.find_all(True, recursive=False)
        if el.name not in {"script", "style", "noscript"}
    )
    # Also get all direct text from body
    body_text_words = len(body_clone_text.split())

    # Step 3: Count external scripts (proxy for JS bundle complexity)
    external_scripts = soup.find_all("script", src=True)
    script_count = len(external_scripts)

    # Step 4: Check noscript quality (a good noscript fallback is SSR evidence)
    noscript_tags = soup.find_all("noscript")
    noscript_word_count = sum(
        len(ns.get_text(strip=True).split()) for ns in noscript_tags
    )

    # Classification logic
    if detected_framework:
        if body_text_words < _EMPTY_BODY_WORD_THRESHOLD:
            # Strong render gap: framework detected + near-empty body
            return {
                "framework": detected_framework,
                "body_text_words": body_text_words,
                "script_count": script_count,
                "partial": False,
                "evidence": (
                    f"Detected {detected_framework} SPA with only {body_text_words} words of "
                    f"server-rendered text and {script_count} external script file(s). "
                    "Content is almost certainly assembled by JavaScript at runtime. "
                    "AI crawlers using plain HTTP (no browser) will see an empty page shell, "
                    "making most content-dependent audit findings unreliable."
                ),
            }
        elif body_text_words < _THIN_BODY_WORD_THRESHOLD and script_count > _SCRIPT_COUNT_THRESHOLD:
            # Partial SSR: framework detected + thin body + many scripts
            return {
                "framework": detected_framework,
                "body_text_words": body_text_words,
                "script_count": script_count,
                "partial": True,
                "evidence": (
                    f"Detected {detected_framework} with possible partial server-side rendering: "
                    f"{body_text_words} server-rendered words, {script_count} external scripts. "
                    "Some page content may only appear after JavaScript execution. "
                    "Content-dependent audit findings below may be incomplete."
                ),
            }

    # No framework marker — but check for near-empty body with many scripts
    # (some SPAs don't leave obvious framework markers in raw HTML)
    if body_text_words < _EMPTY_BODY_WORD_THRESHOLD and script_count >= 5 and noscript_word_count < 20:
        return {
            "framework": None,
            "body_text_words": body_text_words,
            "script_count": script_count,
            "partial": False,
            "evidence": (
                f"Page has only {body_text_words} words of server-rendered body text "
                f"but {script_count} external scripts and minimal <noscript> fallback "
                f"({noscript_word_count} words). This pattern is consistent with a "
                "client-side-rendered SPA. No specific framework was identified. "
                "Content-dependent audit findings may not reflect what AI crawlers see."
            ),
        }

    return None


def emit_js_render_finding(
    gap_info: dict,
    skill_prefix: str,
    findings: list[Finding],
    idx: list[int],
) -> None:
    """
    Emit a JS-render gap Finding into the findings list.

    Severity:
      - 'high' for full render gap (near-empty body)
      - 'medium' for partial SSR warning
    """
    is_partial = gap_info.get("partial", False)
    framework = gap_info.get("framework")
    body_words = gap_info.get("body_text_words", 0)
    script_count = gap_info.get("script_count", 0)
    framework_label = framework or "an unidentified JS framework"

    severity = "medium" if is_partial else "high"
    title_prefix = "Partial JS rendering detected" if is_partial else "Page relies on JavaScript rendering"

    findings.append(make_finding(
        skill_prefix=skill_prefix,
        index=idx[0],
        title=f"{title_prefix} — AI crawlers see reduced content",
        severity=severity,
        evidence=gap_info["evidence"],
        action_summary=(
            f"The page is built with {framework_label} and requires JavaScript execution "
            f"to render its content ({body_words} words visible server-side). "
            "To improve AI discoverability: (1) Enable Server-Side Rendering (SSR) or "
            "Static Site Generation (SSG) for key pages, (2) Ensure critical content "
            "(headings, structured data, meta tags) is present in server-rendered HTML, "
            "(3) Add a descriptive <noscript> fallback, and (4) Verify your pages with "
            "`curl -L <url> | grep -c '<p>'` to confirm server-rendered paragraph count."
        ),
        action_priority=severity,
    ))
    idx[0] += 1
