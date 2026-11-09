"""Canonical non-feed XML, KML and GPX extraction and custody regression."""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun
from skeleton.ai.webcrawler.xml_documents import XMLDocumentError, extract_xml_evidence

API = b'''<?xml version="1.0" encoding="UTF-8"?>
<record><title>Flight engine schema</title>
<description>Archived aircraft stability and wind vector simulation.</description>
<access_token>SHOULD_NOT_RETAIN_SECRET</access_token>
<remote href="https://outside.example.net/forbidden">Reference only</remote>
</record>'''
GPX = b'''<gpx version="1.1"><trk><name>Coastal flight route</name><trkseg><trkpt lat="1.1" lon="2.2"><ele>125.0</ele><name>Elevation marker</name></trkpt></trkseg></trk></gpx>'''
KML = b'''<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Aircraft map</name><Placemark><name>Original airport</name><description>Flight archive location.</description></Placemark></Document></kml>'''
DOC = ("application/xml", API)
MAP = ("application/vnd.google-earth.kml+xml", KML)
ROUTE = ("application/gpx+xml", GPX)


class XMLProjectionTests(unittest.TestCase):
    def test_xml_text_is_searchable_with_labeled_paths(self):
        row = extract_xml_evidence(API)
        self.assertIn("record.description: Archived aircraft", row.text)
        self.assertEqual(row.title, "Flight engine schema")
        self.assertEqual(row.links, ())
        self.assertFalse(row.reference_trusted)

    def test_credentials_are_redacted_not_scheduled(self):
        row = extract_xml_evidence(API)
        self.assertNotIn("SHOULD_NOT_RETAIN_SECRET", row.text)
        self.assertIn("[redacted sensitive XML element]", row.text)
        self.assertFalse(row.body_executed)

    def test_gpx_and_kml_supported_without_requesting_embedded_links(self):
        self.assertIn("Elevation marker", extract_xml_evidence(GPX).text)
        self.assertIn("Original airport", extract_xml_evidence(KML).text)

    def test_document_is_truncated_only_when_necessary(self):
        row = extract_xml_evidence(API, max_chars=64)
        self.assertTrue(row.truncated)
        self.assertEqual(len(row.text), 64)

    def test_external_entities_rejected(self):
        for attack in (
            b'<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///etc/passwd">]><foo>&x;</foo>',
            b'<!ENTITY x "bar"><foo>&x;</foo>',
            b'<!DOCTYPE foo><foo>ok</foo>',
        ):
            with self.subTest(attack=attack), self.assertRaises(XMLDocumentError):
                extract_xml_evidence(attack)

    def test_invalid_xml_and_unsupported_encoding_rejected(self):
        for attack in (b"<open>", b'<?xml version="1.0" encoding="ISO-8859-1"?><a>x</a>', b"\xff\xfe<"):
            with self.subTest(attack=attack), self.assertRaises(XMLDocumentError):
                extract_xml_evidence(attack)

    def test_overdeep_xml_rejected(self):
        raw = (b"<a>" * 40) + b"text" + (b"</a>" * 40)
        with self.assertRaises(XMLDocumentError):
            extract_xml_evidence(raw)

    def test_node_bound_is_hard(self):
        raw = b"<root>" + b"<entry>value</entry>" * 20 + b"</root>"
        with self.assertRaises(XMLDocumentError):
            extract_xml_evidence(raw, max_nodes=8)

    def test_empty_xml_does_not_produce_fake_evidence(self):
        with self.assertRaises(XMLDocumentError):
            extract_xml_evidence(b"<root><nothing/></root>")


class XMLScriptedTransport:
    timeout_seconds = 4
    transport_mode = "scripted_inert_xml_evidence"
    def __init__(self, mime, body):
        self.mime, self.body, self.calls = mime, body, []

    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchResponse(url, 200, {"content-type": "text/plain"}, b"User-agent: *\nAllow: /\n", time.time())
        if url != "https://example.com/schema":
            raise AssertionError("unexpected destination")
        if len(self.body) > max_bytes:
            raise AssertionError("uncapped test body")
        return FetchResponse(url, 200, {"content-type": self.mime}, self.body, time.time())


class CanonicalXMLTests(unittest.TestCase):
    def make_run(self, fetcher):
        now = time.time()
        return CrawlRun.create(CrawlRequest(
            seed_urls=("https://example.com/schema",),
            allowed_hosts=("example.com",),
            max_depth=0, max_requests=4, max_documents=2,
            max_response_bytes=4096, max_total_bytes=12288,
        ), scope={"tenant_id":"tenant", "owner_id":"owner"}, consent={
            "consent_id":"xml-source-rights",
            "capture_acknowledged":True,
            "source_rights_acknowledged":True,
            "expires_at":now+3600,
        }, now=now, fetcher=fetcher), now

    def advance(self, run, at):
        with patch("skeleton.ai.webcrawler.operations.time.time", return_value=at):
            run.run_slice(max_steps=1,max_seconds=1,authorize=lambda:None,
                cancelled=lambda:False,on_checkpoint=lambda snapshot,event:None)

    def test_generic_xml_and_geospatial_xml_reach_retrieval_not_discovery(self):
        for mime, content in (DOC, MAP, ROUTE):
            with self.subTest(mime=mime):
                transport = XMLScriptedTransport(mime, content)
                run, now = self.make_run(transport)
                self.advance(run, now+1)
                self.advance(run, now+3)
                state=run.snapshot()
                self.assertEqual(state["usage"]["documents"],1)
                self.assertEqual(state["usage"]["requests"],2)
                self.assertEqual(state["frontier"],[])
                self.assertEqual(next(iter(state["sources"].values()))["review_state"],"unreviewed")
                self.assertEqual(CrawlRun.from_snapshot(state,fetcher=transport).snapshot(),state)

    def test_generic_xml_secret_does_not_leak_to_search(self):
        transport=XMLScriptedTransport(*DOC)
        run, now=self.make_run(transport)
        self.advance(run,now+1);self.advance(run,now+3)
        source=next(iter(run.snapshot()["sources"].values()))
        self.assertNotIn("SHOULD_NOT_RETAIN_SECRET",source["text"])
        self.assertTrue(run.search("aircraft")["hits"])
        self.assertFalse(source["provenance"]["training_permission"])

    def test_malformed_non_feed_xml_is_not_retained(self):
        transport=XMLScriptedTransport("application/xml",b'<!DOCTYPE x><x>ok</x>')
        run,now=self.make_run(transport)
        self.advance(run,now+1);self.advance(run,now+3)
        self.assertEqual(run.snapshot()["usage"]["documents"],0)
        self.assertEqual(run.snapshot()["frontier"],[])


if __name__=="__main__":
    unittest.main()
