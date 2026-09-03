# UX Engagement Heuristics

## Principles (adapted from Nielsen's 10 Heuristics for AI-era web engagement)

### 1. Immediate Orientation
**Rule**: A visitor should understand what the site offers within 5 seconds.
**Signals**: Clear H1, non-empty meta description (50–160 chars), above-the-fold value proposition.
**Finding threshold**: Meta description absent or <20 chars → medium finding.

### 2. Consistent & Predictable Navigation
**Rule**: Users navigating from AI-generated summaries arrive mid-journey. Navigation must be discoverable.
**Signals**: `<nav>` element present; site has ≥3 internal links in the main content area.
**Finding threshold**: No `<nav>` element → high finding.

### 3. Clear Heading Hierarchy
**Rule**: Headings must form a logical outline (h1 → h2 → h3), never skipping levels.
**Signals**: Exactly one `<h1>`. Heading levels sequential.
**Finding thresholds**:
  - Zero `<h1>` → high finding
  - Multiple `<h1>` → high finding
  - Skipped heading level (e.g., h1 → h3) → medium finding

### 4. Readable Content
**Rule**: Content should be readable at a general audience level.
**Signal**: Average sentence length ≤ 25 words.
**Finding threshold**: Average sentence length > 30 words → medium finding.

### 5. Scannability
**Rule**: Long-form content must be broken up with lists, tables, or visual hierarchy.
**Signal**: Pages >500 words must contain at least one `<ul>`, `<ol>`, or `<table>`.
**Finding threshold**: Long page with no list/table → medium finding.

### 6. Clear Call to Action
**Rule**: Every page should have a primary next step for the visitor.
**Signal**: At least one `<a>`, `<button>`, or `<form>` with an action verb (Get, Start, Download, Try, Buy, Sign up, Contact, Learn, Book).
**Finding threshold**: No CTA detected → high finding.

### 7. Mobile Accessibility
**Rule**: Mobile users must not be penalised.
**Signal**: `<meta name="viewport" content="width=device-width,...">` present.
**Finding threshold**: Missing viewport meta → high finding.

### 8. Accessible Images
**Rule**: Informational images must have descriptive alt text.
**Signal**: All `<img>` elements have non-empty `alt` attributes.
**Finding threshold**: >20% of images missing alt text → medium finding.

### 9. Social & AI Preview Metadata
**Rule**: AI chatbots and social platforms use Open Graph metadata to summarise pages.
**Signals**: `og:title`, `og:description`, `og:image` all present.
**Finding thresholds**:
  - `og:title` missing → medium finding
  - `og:description` missing → medium finding
  - `og:image` missing → low finding

### 10. Orientation for AI-referred Visitors
**Rule**: AI systems summarise pages for users before they click. The page must be able to stand on its own.
**Signal**: Page has a meta description AND an H1 AND at least one substantive paragraph.
**Finding threshold**: All three missing simultaneously → high finding.
