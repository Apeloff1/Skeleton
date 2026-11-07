"""RSS 1.0 RDF feed discovery and retained HTML semantic landmarks."""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch
from skeleton.ai.webcrawler.core import FetchResponse, CrawlPolicy, extract_document
from skeleton.ai.webcrawler.operations import CrawlRun, CrawlRequest
from skeleton.ai.webcrawler.structured_discovery import (
    UnsupportedDiscoveryRoot, DiscoveryError, parse_structured_discovery,
)
from skeleton.ai.webcrawler.html_landmarks import (
    HTMLLandmarkError, extract_html_landmarks,
)

POLICY=CrawlPolicy(allowed_hosts=frozenset({"example.com"}))
RSS1=b'''<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/">
 <channel rdf:about="https://example.com/feed.rdf">
  <title>Aviation research</title><link>https://example.com/</link>
  <items><rdf:Seq><rdf:li rdf:resource="https://outside.example.net/private"/></rdf:Seq></items>
 </channel>
 <item rdf:about="https://example.com/a">
  <title>Aircraft stability</title><link>https://example.com/articles/flight</link>
 </item>
 <item rdf:about="https://example.com/b">
  <title>Wing model</title><link>https://outside.example.net/other-host</link>
 </item>
 <item rdf:about="https://example.com/c">
  <title>Coastal flight</title><link>/articles/coast</link>
 </item>
</rdf:RDF>'''
HTML=b'''<!doctype html><html><head>
<meta name="description" content="Historic aerospace modeling paper">
<title>Wing research</title>
<script type="application/javascript">window.SECRET_SCRIPT="BAD_SCRIPT";</script>
</head><body>
<main><article>
<h1>Airframe research</h1><h2>Lift and drag coefficients</h2>
<figure><img src="https://outside.example.net/image">
<figcaption>Wing loading chart</figcaption></figure>
<blockquote>Measured stability under crosswinds</blockquote>
<details><summary>Engine coefficient notes</summary></details>
<p>Aircraft flight science.</p>
</article></main>
</body></html>'''


class DirectSourceTests(unittest.TestCase):
    def test_rss1_rdf_follows_only_item_link(self):
        report=parse_structured_discovery(
            RSS1,media_type="application/rdf+xml",
            document_url="https://example.com/feed.rdf",policy=POLICY,
        )
        self.assertEqual(report.kind,"rss1_feed")
        self.assertEqual(report.links,(
            "https://example.com/articles/flight",
            "https://example.com/articles/coast",
        ))
        self.assertFalse(report.new_authority_granted)
        self.assertFalse(report.source_text_retained)

    def test_arbitrary_rdf_not_interpreted_as_feed(self):
        source=b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
            <rdf:Description rdf:about="https://example.com/private"/></rdf:RDF>'''
        with self.assertRaises(UnsupportedDiscoveryRoot):
            parse_structured_discovery(
                source,media_type="application/rdf+xml",
                document_url="https://example.com/rdf",policy=POLICY,
            )

    def test_doctype_and_entity_fenced(self):
        source=b'''<!DOCTYPE rdf:RDF [<!ENTITY x SYSTEM "file:///etc/passwd">]>
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">&x;</rdf:RDF>'''
        with self.assertRaises(DiscoveryError):
            parse_structured_discovery(
                source,media_type="application/rdf+xml",
                document_url="https://example.com/feed.rdf",policy=POLICY,
            )

    def test_html_landmarks_preserve_headings_not_scripts(self):
        report=extract_html_landmarks(HTML.decode())
        self.assertIn("Heading 1: Airframe research",report.text)
        self.assertIn("Heading 2: Lift and drag coefficients",report.text)
        self.assertIn("Figure: Wing loading chart",report.text)
        self.assertIn("Quotation: Measured stability",report.text)
        self.assertIn("Document description:",report.text)
        self.assertNotIn("BAD_SCRIPT",report.text)
        self.assertNotIn("outside.example.net",report.text)
        self.assertEqual(report.links,())
        self.assertFalse(report.body_executed)

    def test_html_landmark_limit_and_overlarge_meta(self):
        with self.assertRaises(HTMLLandmarkError):
            extract_html_landmarks('<meta name="description" content="'+("x"*1025)+'">')

    def test_html_canonical_document_contains_semantic_projection(self):
        response=FetchResponse("https://example.com/flight",200,
                               {"content-type":"text/html"},HTML,time.time())
        doc=extract_document(response,response.url)
        self.assertIn("Heading 1: Airframe research",doc.text)
        self.assertIn("Figure: Wing loading chart",doc.text)
        self.assertNotIn("BAD_SCRIPT",doc.text)


class Transport:
    timeout_seconds=4
    transport_mode="scripted_rss1_and_html"
    def __init__(self,body,mime):
        self.body,self.mime,self.calls=body,mime,[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/source":
            raise AssertionError("unexpected network request")
        return FetchResponse(url,200,{"content-type":self.mime},self.body,time.time())


class CanonicalRSS1AndHTMLTests(unittest.TestCase):
    def capture(self,body,mime):
        now=time.time()
        transport=Transport(body,mime)
        run=CrawlRun.create(
            CrawlRequest(
                seed_urls=("https://example.com/source",),
                allowed_hosts=("example.com",),max_depth=1,
                max_requests=4,max_documents=2,
                max_response_bytes=65536,max_total_bytes=131072,
            ),
            scope={"tenant_id":"tenant","owner_id":"owner"},
            consent={"consent_id":"rss1-landmark-rights",
                     "capture_acknowledged":True,"source_rights_acknowledged":True,
                     "expires_at":now+3600},
            now=now,fetcher=transport,
        )
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",
                       return_value=now+offset):
                run.run_slice(max_steps=1,max_seconds=1,
                              authorize=lambda:None,cancelled=lambda:False,
                              on_checkpoint=lambda snapshot,event:None)
        return run,transport

    def test_rss1_real_worker_frontier_admission(self):
        run,transport=self.capture(RSS1,"application/rdf+xml")
        state=run.snapshot()
        self.assertEqual(state["usage"]["requests"],2)
        self.assertEqual(state["usage"]["documents"],0)
        self.assertEqual({r["url"] for r in state["frontier"]},{
            "https://example.com/articles/flight",
            "https://example.com/articles/coast",
        })
        self.assertEqual(len(transport.calls),2)
        self.assertEqual(
            CrawlRun.from_snapshot(state,fetcher=transport).snapshot(),state,
        )

    def test_html_landmarks_enter_unreviewed_evidence(self):
        run,transport=self.capture(HTML,"text/html")
        state=run.snapshot()
        self.assertEqual(state["usage"]["documents"],1)
        record=run.sources()[0]
        self.assertIn("Heading 1: Airframe research",record["text"])
        self.assertFalse(record["provenance"]["training_permission"])
        self.assertEqual(record["review_state"],"unreviewed")
        self.assertEqual(len(transport.calls),2)


if __name__=="__main__":
    unittest.main()
