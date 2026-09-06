"""
skills/audit-orchestrator/scripts/render_html.py

B5: Self-contained HTML report renderer.
Generates a single HTML file with inline CSS, severity-coloured findings,
executive summary, root-cause groups, and copy buttons on snippets.
"""
from __future__ import annotations

import html
import json
from typing import Any


_SEVERITY_COLORS = {
    "critical": "#dc2626",
    "high": "#ea580c",
    "medium": "#ca8a04",
    "low": "#65a30d",
}

_SEVERITY_BG = {
    "critical": "#fef2f2",
    "high": "#fff7ed",
    "medium": "#fefce8",
    "low": "#f7fee7",
}


def render_html_report(report: dict[str, Any]) -> str:
    """Render a full audit report dict as a self-contained HTML string."""
    site = html.escape(report.get("site", "Unknown"))
    audited_at = html.escape(report.get("audited_at", ""))
    summary = report.get("summary", {})
    headline = html.escape(summary.get("headline", ""))
    findings = report.get("findings", [])
    root_causes = report.get("root_causes", [])
    metadata = report.get("metadata", {})

    # Build severity summary pills
    severity_pills = ""
    for sev in ("critical", "high", "medium", "low"):
        count = summary.get(sev, 0)
        color = _SEVERITY_COLORS[sev]
        severity_pills += (
            f'<span style="display:inline-block;padding:4px 12px;border-radius:9999px;'
            f'background:{color};color:white;font-weight:600;margin-right:8px;font-size:13px;">'
            f'{sev.upper()}: {count}</span>'
        )

    # Build root-cause section
    rc_html = ""
    if root_causes:
        rc_html = '<h2 style="margin-top:32px;">Root-Cause Clusters</h2>'
        for rc in root_causes:
            label = html.escape(rc.get("label", rc.get("cause", "")))
            ids = ", ".join(rc.get("finding_ids", []))
            rc_html += (
                f'<div style="margin:8px 0;padding:8px 12px;background:#f1f5f9;border-radius:8px;">'
                f'<strong>{label}</strong> ({rc["count"]} finding(s)): {ids}</div>'
            )

    # Build findings section
    findings_html = ""
    for f in findings:
        sev = f.get("severity", "medium")
        color = _SEVERITY_COLORS.get(sev, "#6b7280")
        bg = _SEVERITY_BG.get(sev, "#f9fafb")
        fid = html.escape(f.get("id", ""))
        title = html.escape(f.get("title", ""))
        evidence = html.escape(f.get("evidence", ""))
        confidence = f.get("confidence", "")
        action = f.get("suggested_action", {})
        action_summary = html.escape(action.get("summary", ""))
        snippet = action.get("snippet", "")

        confidence_badge = ""
        if confidence:
            confidence_badge = (
                f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;'
                f'background:#e0e7ff;color:#3730a3;font-size:11px;margin-left:8px;">'
                f'{html.escape(confidence)}</span>'
            )

        snippet_block = ""
        if snippet:
            escaped_snippet = html.escape(snippet)
            # Use a unique ID for each copy button
            snippet_id = f"snippet-{fid}"
            snippet_block = (
                f'<div style="margin-top:8px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<strong style="font-size:12px;color:#6b7280;">Template snippet:</strong>'
                f'<button onclick="navigator.clipboard.writeText(document.getElementById(\'{snippet_id}\').textContent)'
                f'.then(()=>this.textContent=\'Copied!\')" '
                f'style="padding:2px 8px;border:1px solid #d1d5db;border-radius:4px;'
                f'background:white;cursor:pointer;font-size:11px;">Copy</button></div>'
                f'<pre id="{snippet_id}" style="background:#1e293b;color:#e2e8f0;padding:12px;'
                f'border-radius:6px;overflow-x:auto;font-size:12px;margin-top:4px;">{escaped_snippet}</pre></div>'
            )

        findings_html += (
            f'<div style="margin:16px 0;padding:16px;border-left:4px solid {color};'
            f'background:{bg};border-radius:0 8px 8px 0;">'
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'<span style="font-weight:700;color:{color};">{fid}</span>'
            f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;'
            f'background:{color};color:white;font-size:11px;font-weight:600;">{sev.upper()}</span>'
            f'{confidence_badge}'
            f'</div>'
            f'<h3 style="margin:8px 0 4px;">{title}</h3>'
            f'<p style="color:#374151;font-size:14px;line-height:1.5;">{evidence}</p>'
            f'<div style="margin-top:8px;padding:8px 12px;background:rgba(255,255,255,0.7);'
            f'border-radius:6px;">'
            f'<strong style="font-size:12px;color:#6b7280;">Suggested action:</strong>'
            f'<p style="margin:4px 0 0;font-size:13px;">{action_summary}</p>'
            f'{snippet_block}'
            f'</div></div>'
        )

    skills_run = ", ".join(metadata.get("skills_run", []))
    skills_failed = ", ".join(metadata.get("skills_failed", [])) or "none"
    duration = metadata.get("duration_seconds", 0)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brand AI Readiness Audit — {site}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         max-width: 900px; margin: 0 auto; padding: 24px; background: #f8fafc; color: #1e293b; }}
  h1 {{ font-size: 24px; margin-bottom: 4px; }}
  h2 {{ font-size: 18px; color: #475569; margin-bottom: 12px; }}
  .meta {{ color: #64748b; font-size: 13px; margin-bottom: 16px; }}
  .headline {{ font-size: 16px; color: #0f172a; font-weight: 500; margin: 12px 0; padding: 12px;
               background: #eff6ff; border-radius: 8px; border-left: 4px solid #3b82f6; }}
</style>
</head>
<body>
<h1>Brand AI Readiness Audit</h1>
<p class="meta">{site} &bull; {audited_at} &bull; {duration}s &bull; Skills: {skills_run} &bull; Failed: {skills_failed}</p>

<div class="headline">{headline}</div>

<div style="margin:16px 0;">{severity_pills}</div>

<p style="font-size:15px;color:#475569;">Total findings: <strong>{summary.get('total_findings', 0)}</strong></p>

{rc_html}

<h2 style="margin-top:32px;">Findings</h2>
{findings_html}

<footer style="margin-top:40px;padding-top:16px;border-top:1px solid #e2e8f0;color:#94a3b8;font-size:12px;">
Generated by Brand AI Readiness Audit &mdash; Adobe University Hackathon 2026
</footer>
</body>
</html>"""
