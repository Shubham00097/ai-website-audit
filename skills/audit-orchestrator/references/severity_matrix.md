# Severity Assignment Matrix

## Severity Levels

| Level | Meaning | Example |
|---|---|---|
| **critical** | Directly prevents AI from accessing or quoting the site. Must fix immediately. | WAF silently blocks GPTBot despite robots.txt Allow |
| **high** | Significantly reduces AI discoverability or user engagement. Fix soon. | No JSON-LD structured data found on any page |
| **medium** | Reduces AI citability or engagement quality. Fix when possible. | Meta description missing on homepage |
| **low** | Minor improvement opportunity. Nice to have. | og:image missing |

## Rules

1. **Declared vs. Actual mismatch** → always `critical`
2. **AI cloaking / prompt injection** → always `critical`
3. **YMYL schema without credentials** → always `critical`
4. **sameAs placeholder (#)** → always `critical`
5. **Live AI bot returns 403 or 429** → `high`
6. **No structured data whatsoever** → `high`
7. **Required schema fields missing** → `high`
8. **No CTA on page** → `high`
9. **No <nav> element** → `high`
10. **No <h1>** or **multiple <h1>** → `high`
11. **No mobile viewport** → `high`
12. **Content >18 months stale** → `high`
13. **Dead sameAs links** → `high`
14. **Missing meta description** → `medium`
15. **Skipped heading levels** → `medium`
16. **Low statistical density** → `medium`
17. **No author byline** → `medium`
18. **Missing Open Graph tags** → `medium`
19. **Images without alt text** → `medium`
20. **llms.txt missing** → `medium`
21. **sitemap.xml missing** → `medium`
22. **og:image missing** → `low`
23. **Blog cadence gap >90 days** → `low`
