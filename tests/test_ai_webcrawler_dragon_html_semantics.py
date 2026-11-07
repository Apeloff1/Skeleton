"""Inert HTML table/JSON-LD semantics through canonical source acquisition."""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.html_semantics import (
    HTMLSemanticError, extract_html_semantics,
)
from skeleton.ai.webcrawler.core import FetchResponse, extract_document
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun

PAGE = b'''<html><head><title>Flight Manual</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Article","headline":"Aircraft design ledger",
"access_token":"DO_NOT_KEEP_TOKEN","author":{"name":"Original designer"}}
</script></head>
<body><h1>Flight stability</h1><table><tr><th>Model</th><th>Speed</th></tr>
<tr><td>Falcon</td><td>450 knots</td></tr>
<tr><td>Sparrow</td><td>220 knots</td></tr></table>
<a href="/flight-chapter">Continue</a>
</body></html>'''

class SemanticsParserTests(unittest.TestCase):
    def test_real_html_table_projects_field_labeled_rows(self):
        result = extract_html_semantics(PAGE.decode())
        self.assertIn("Table 1 row 1: Model: Falcon; Speed: 450 knots", result.text)
        self.assertIn("Table 1 row 2: Model: Sparrow; Speed: 220 knots", result.text)
        self.assertEqual(result.tables, 1)
        self.assertEqual(result.table_rows, 2)
        self.assertEqual(result.links, ())

    def test_jsonld_is_inert_text_not_raw_script_execution(self):
        result = extract_html_semantics(PAGE.decode())
        self.assertIn("Aircraft design ledger", result.text)
        self.assertIn("Original designer", result.text)
        self.assertNotIn("DO_NOT_KEEP_TOKEN", result.text)
        self.assertFalse(result.body_executed)
        self.assertFalse(result.reference_trusted)

    def test_script_with_other_media_type_is_not_ingested(self):
        raw = '<script>alert("execute me")</script><p>visible page</p>'
        self.assertEqual(extract_html_semantics(raw).text, "")

    def test_malformed_jsonld_is_counted_but_not_executed(self):
        raw = '<script type="application/ld+json">{bad}</script>'
        result = extract_html_semantics(raw)
        self.assertEqual(result.jsonld_blocks, 1)
        self.assertEqual(result.malformed_jsonld, 1)
        self.assertEqual(result.text, "")

    def test_jsonld_does_not_create_frontier_links(self):
        raw = '<script type="application/ld+json">{"url":"https://outside.example.net/evil"}</script>'
        row = extract_html_semantics(raw)
        self.assertEqual(row.links, ())
        self.assertIn("outside.example.net", row.text)

    def test_many_large_table_cells_refuse_to_parse(self):
        raw = '<table><tr><td>' + "X" * 2049 + '</td></tr></table>'
        with self.assertRaises(HTMLSemanticError):
            extract_html_semantics(raw)

    def test_semantic_char_limit_is_finite(self):
        raw = "<table><tr><td>" + "R" * 300 + "</td></tr></table>"
        result = extract_html_semantics(raw, max_chars=128)
        self.assertTrue(result.truncated)

    def test_too_many_jsonld_blocks_rejected(self):
        raw = '<script type="application/ld+json">{"a": 1}</script>' * 9
        with self.assertRaises(HTMLSemanticError):
            extract_html_semantics(raw)

    def test_simple_document_extraction_attaches_semantic_evidence(self):
        from skeleton.ai.webcrawler.core import extract_document
        document = extract_document(FetchResponse(
            "https://example.com/flight",200,
            {"content-type":"text/html"},PAGE,time.time(),
        ),"https://example.com/flight")
        self.assertIn("450 knots",document.text)
        self.assertIn("Original designer",document.text)
        self.assertEqual(document.links,("https://example.com/flight-chapter",))


class HTMLScriptedTransport:
    timeout_seconds=4
    transport_mode="scripted_html_semantics"
    def __init__(self):
        self.calls=[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchResponse(url,200,{"content-type":"text/plain"},b"User-agent: *\nAllow: /\n",time.time())
        if url not in ("https://example.com/flight","https://example.com/flight-chapter"):
            raise AssertionError("unexpected network destination")
        body=PAGE if url.endswith("/flight") else b"<html><title>Chapter</title>Flight chapter text.</html>"
        return FetchResponse(url,200,{"content-type":"text/html"},body,time.time())


class HTMLCanonicalIntegrationTests(unittest.TestCase):
    def test_source_table_jsonld_and_html_links_reach_real_worker(self):
        at=time.time()
        transport=HTMLScriptedTransport()
        run=CrawlRun.create(CrawlRequest(
            seed_urls=("https://example.com/flight",),
            allowed_hosts=("example.com",),max_depth=1,
            max_requests=4,max_documents=2,
            max_response_bytes=4096,max_total_bytes=16384,
            min_host_delay_seconds=.25,
        ),scope={"tenant_id":"t","owner_id":"o"},consent={
            "consent_id":"html-semantics-consent","capture_acknowledged":True,
            "source_rights_acknowledged":True,"expires_at":at+3600,
        },now=at,fetcher=transport)
        for offset in (1,3,5):
            with patch("skeleton.ai.webcrawler.operations.time.time",return_value=at+offset):
                run.run_slice(max_steps=1,max_seconds=1,authorize=lambda:None,
                    cancelled=lambda:False,on_checkpoint=lambda snapshot,event:None)
        snap=run.snapshot()
        self.assertEqual(snap["usage"]["documents"],2)
        self.assertTrue(run.search("450 knots")["hits"])
        self.assertEqual(transport.calls,[
            "https://example.com/robots.txt",
            "https://example.com/flight",
            "https://example.com/flight-chapter",
        ])
        first=next(s for s in run.sources() if s["canonical_url"]=="https://example.com/flight")
        self.assertNotIn("DO_NOT_KEEP_TOKEN",first["text"])
        self.assertFalse(first["provenance"]["training_permission"])
        self.assertEqual(CrawlRun.from_snapshot(snap,fetcher=transport).snapshot(),snap)


if __name__=="__main__":
    unittest.main()
