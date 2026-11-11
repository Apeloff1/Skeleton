"""Inert schema.org Microdata, RDFa and Microformats2 source observations."""
from __future__ import annotations
import time
import unittest
from unittest.mock import patch
from skeleton.ai.webcrawler.html_structured_entities import (
    extract_html_structured_entities,StructuredHTMLError,
)
from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest,CrawlRun

HTML=b'''<html><head><title>Research</title></head><body><main>
<article itemscope itemtype="https://schema.org/ScholarlyArticle">
<h1 itemprop="headline">New aircraft stability model</h1>
<p itemprop="description">Bounded scene and control study.</p>
<span itemprop="author">Adrian Researcher</span>
<a itemprop="url" href="https://outside.example.net/private">Hidden link</a>
<meta itemprop="identifier" content="SECRET_METADATA"/>
</article>
<section typeof="schema:SoftwareApplication">
<h2 property="schema:name">Original flight simulator</h2>
<p property="schema:description">Deterministic scene rendering.</p>
<a property="schema:url" href="https://outside.example.net/hidden">URL not projected</a>
</section>
<div class="h-entry">
<h2 class="p-name">Archive record</h2>
<p class="p-summary">Research synopsis for physics.</p>
<a class="u-url" href="https://outside.example.net/secret">not indexed</a>
</div>
<script type="application/javascript">var x="SECRET_SCRIPT";</script>
<iframe src="https://outside.example.net/private"></iframe>
</main></body></html>'''

class DirectTests(unittest.TestCase):
    def test_three_families_and_no_attribute_url_leaks(self):
        result=extract_html_structured_entities(HTML.decode())
        self.assertEqual(result.items,3)
        self.assertEqual(result.families,("microdata","microformats2","rdfa"))
        for phrase in ("New aircraft stability model","Original flight simulator",
                       "Archive record","Deterministic scene rendering"):
            self.assertIn(phrase,result.text)
        for secret in ("SECRET_METADATA","SECRET_SCRIPT","outside.example.net",
                       "URL not projected","not indexed"):
            self.assertNotIn(secret,result.text)
        self.assertEqual(result.links,())
        self.assertFalse(result.body_executed)
        self.assertFalse(result.reference_trusted)
    def test_remote_ontology_is_not_interpreted(self):
        source='<div itemscope itemtype="https://foreign.example/Secret"><h1 itemprop="name">X</h1></div>'
        self.assertEqual(extract_html_structured_entities(source).items,0)
    def test_meta_content_is_never_projected(self):
        source=('<div itemscope itemtype="https://schema.org/Article">'
                '<meta itemprop="name" content="SECRET"/>'
                '<h1 itemprop="name">Safe headline</h1></div>')
        result=extract_html_structured_entities(source)
        self.assertIn("Safe headline",result.text)
        self.assertNotIn("SECRET",result.text)
    def test_sensitive_visible_text_is_not_promoted_as_property(self):
        source=('<div typeof="schema:Article">'
                '<p property="name">api_key=SECRET</p>'
                '<p property="description">https://outside.example.net/private</p></div>')
        row=extract_html_structured_entities(source)
        self.assertNotIn("SECRET",row.text)
        self.assertNotIn("outside.example.net",row.text)
    def test_markup_depth_and_length_limits(self):
        with self.assertRaises(StructuredHTMLError):
            extract_html_structured_entities("<div>"*70+"x"+"</div>"*70)
        with self.assertRaises(StructuredHTMLError):
            extract_html_structured_entities("x"*2500001)
    def test_finite_property_budget_is_visible(self):
        body=('<div itemscope itemtype="https://schema.org/Article">'
              +'<p itemprop="name">x</p>'*600+'</div>')
        row=extract_html_structured_entities(body)
        self.assertEqual(row.properties,512)
        self.assertTrue(row.truncated)
    def test_incomplete_property_not_fabricated(self):
        row=extract_html_structured_entities(
            '<div typeof="schema:Article"><p property="name">Incomplete'
        )
        self.assertEqual(row.items,1)
        self.assertNotIn("Incomplete",row.text)

class Transport:
    timeout_seconds=4
    transport_mode="scripted_structured_html"
    def __init__(self,header=None):
        self.header=header or {}
        self.calls=[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/article":
            raise AssertionError("HTML itemtype initiated an external request")
        return FetchResponse(url,200,{"content-type":"text/html",**self.header},
                             HTML,time.time())

class CanonicalTests(unittest.TestCase):
    def capture(self,header=None):
        now=time.time()
        fetcher=Transport(header)
        run=CrawlRun.create(
            CrawlRequest(seed_urls=("https://example.com/article",),
                allowed_hosts=("example.com",),max_requests=4,
                max_documents=2,max_depth=1,max_response_bytes=65536,
                max_total_bytes=131072),
            scope={"tenant_id":"t","owner_id":"o"},
            consent={"consent_id":"structured-html-rights",
                "capture_acknowledged":True,"source_rights_acknowledged":True,
                "expires_at":now+3600},now=now,fetcher=fetcher)
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",return_value=now+offset):
                run.run_slice(max_steps=1,max_seconds=1,authorize=lambda:None,
                    cancelled=lambda:False,on_checkpoint=lambda snap,event:None)
        return run,fetcher
    def test_source_receipt_contains_structured_fields(self):
        run,fetcher=self.capture()
        snap=run.snapshot()
        self.assertEqual(snap["usage"]["requests"],2)
        self.assertEqual(snap["usage"]["documents"],1)
        self.assertEqual(len(fetcher.calls),2)
        entry=run.sources()[0]
        self.assertIn("Structured item 1",entry["text"])
        self.assertIn("New aircraft stability model",entry["text"])
        self.assertNotIn("SECRET_METADATA",entry["text"])
        self.assertEqual(entry["review_state"],"unreviewed")
        self.assertFalse(entry["provenance"]["training_permission"])
        self.assertEqual(CrawlRun.from_snapshot(snap,fetcher=fetcher).snapshot(),snap)
    def test_site_noarchive_precedes_semantic_capture(self):
        run,fetcher=self.capture({"x-robots-tag":"noarchive,nofollow"})
        self.assertEqual(run.snapshot()["usage"]["documents"],0)
        self.assertEqual(len(fetcher.calls),2)
        self.assertEqual(run.snapshot()["frontier"],[])

if __name__=="__main__":
    unittest.main()
