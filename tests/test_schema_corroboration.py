"""Regression tests for independent entity-fact corroboration."""
from __future__ import annotations

import importlib.util
import os
import sys
from unittest.mock import patch

from bs4 import BeautifulSoup


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _load_module():
    path = os.path.join(
        _REPO_ROOT, "skills", "structured-data-audit", "scripts", "check_schema.py"
    )
    spec = importlib.util.spec_from_file_location("schema_corroboration_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code
        self.headers = {"Content-Type": "text/html"}


def _page(name="Acme Labs", same_as=True):
    identity = ', "sameAs": "https://www.wikidata.org/wiki/Q1"' if same_as else ""
    return f"""<html><head><script type="application/ld+json">
    {{"@context":"https://schema.org", "@type":"Organization", "name":"{name}",
      "url":"https://acme.example", "foundingDate":"2019-01-01",
      "address":{{"@type":"PostalAddress", "addressLocality":"Pune"}}{identity}}}
    </script></head><body><h1>{name}</h1></body></html>"""


def _source_page(name="Acme Labs"):
    return f"""<html><body><h1 id="firstHeading">{name}</h1>
    <table class="infobox"><tr><th>Founded</th><td>2019</td></tr>
    <tr><th>Headquarters</th><td>Pune</td></tr></table></body></html>"""


def _run(page_html, source_html=None):
    module = _load_module()
    result = (page_html, BeautifulSoup(page_html, "html.parser"))
    with patch.object(module, "fetch_html_and_parse", return_value=result), \
         patch.object(module, "get", return_value=_Response(source_html or "")):
        return module.run("https://acme.example")


def test_matching_wikidata_facts_do_not_emit_corroboration_finding():
    findings = _run(_page(), _source_page())
    assert not [f for f in findings if f.title == "Entity facts disagree across sources"]


def test_mismatched_wikidata_facts_emit_evidence_from_both_sources():
    findings = _run(_page(), _source_page("Different Company"))
    finding = next(f for f in findings if f.title == "Entity facts disagree across sources")
    assert finding.severity == "high"
    assert finding.cause_tag == "trust_signals"
    assert "Acme Labs" in finding.evidence
    assert "Different Company" in finding.evidence


def test_absent_same_as_emits_no_independently_verifiable_presence_finding():
    findings = _run(_page(same_as=False))
    finding = next(
        f for f in findings
        if f.title == "No independently verifiable presence found for this entity"
    )
    assert finding.severity == "medium"
    assert finding.cause_tag == "trust_signals"
