"""
skills/bot-crawlability-audit/scripts/waf_detector.py

Identifies WAF/CDN products from HTTP response headers.
Patterns loaded from references/waf_fingerprints.json.
"""
from __future__ import annotations

import json
import os
from typing import Optional
from requests import Response

_FINGERPRINTS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "references", "waf_fingerprints.json"
)


def _load_fingerprints() -> list[dict]:
    """Load WAF fingerprint patterns from references file."""
    try:
        with open(_FINGERPRINTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("products", [])
    except Exception:
        return []


# Cache fingerprints at module load time — avoid re-reading JSON on every detect_waf() call
_FINGERPRINTS: list[dict] = _load_fingerprints()


def detect_waf(response: Response) -> Optional[str]:
    """
    Match response headers against known WAF/CDN fingerprints.
    Returns the product name if detected, or None.
    Uses module-level cached fingerprints (loaded once per process).
    """
    headers_lower = {k.lower(): v.lower() for k, v in response.headers.items()}

    for product in _FINGERPRINTS:
        matched = True
        for pattern in product.get("header_patterns", []):
            header = pattern["header"].lower()
            if pattern.get("exists"):
                if header not in headers_lower:
                    matched = False
                    break
            elif "contains" in pattern:
                value = headers_lower.get(header, "")
                if pattern["contains"].lower() not in value:
                    matched = False
                    break
        if matched and product.get("header_patterns"):
            return product["name"]

    return None
