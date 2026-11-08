"""Text sitemap acquisition through real robots, scope and budget enforcement."""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import CrawlPolicy,FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest,CrawlRun
from skeleton.ai.webcrawler.structured_discovery import (
    DiscoveryError,parse_plaintext_sitemap,extract_robots_sitemaps,
)


MAP=b"https://example.com/a\nhttps://example.com/b\nhttps://outside.example.net/evil\njavascript:alert(1)\n"
POLICY=CrawlPolicy(allowed_hosts=frozenset({"example.com"}))
PAGE=b"<html><title>Archive</title><body>Archived aircraft research and flight.</body></html>"


class TextSitemapTests(unittest.TestCase):
    def parse(self,body=MAP,**opts):
        return parse_plaintext_sitemap(
            body,document_url="https://example.com/sitemap.txt",
            policy=POLICY,**opts,
        )

    def test_text_sitemap_discovers_only_admissible_source_urls(self):
        result=self.parse()
        self.assertEqual(result.links,(
            "https://example.com/a","https://example.com/b",
        ))
        self.assertEqual(result.kind,"plaintext_sitemap")
        self.assertEqual(result.discarded_entries,2)
        self.assertFalse(result.new_authority_granted)

    def test_duplicate_and_same_page_are_ignored(self):
        body=b"https://example.com/a\nhttps://example.com/a\nhttps://example.com/sitemap.txt\n"
        result=self.parse(body)
        self.assertEqual(result.links,("https://example.com/a",))
        self.assertEqual(result.discarded_entries,2)

    def test_relative_and_credentialed_urls_rejected(self):
        body=b"/relative\nhttps://name:secret@example.com/a\n"
        self.assertEqual(self.parse(body).links,())

    def test_invalid_utf8_and_nul_rejected(self):
        for body in (b"\xff",b"a\x00b",b""):
            with self.subTest(body=body),self.assertRaises(DiscoveryError):
                self.parse(body)

    def test_line_and_entry_limits_are_finite(self):
        result=self.parse(
            b"".join(f"https://example.com/{i}\n".encode() for i in range(100)),
            max_entries=10,
        )
        self.assertTrue(result.capped)
        self.assertEqual(len(result.links),10)

    def test_robots_can_propose_admitted_text_sitemap_seed(self):
        directives="User-agent: *\nSitemap: https://example.com/sitemap.txt\n"
        self.assertEqual(extract_robots_sitemaps(
            directives,origin="https://example.com",policy=POLICY,
        ),("https://example.com/sitemap.txt",))


class SitemapTransport:
    timeout_seconds=3
    transport_mode="scripted_text_sitemap_capture"
    def __init__(self):
        self.calls=[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchResponse(url,200,{"content-type":"text/plain"},
                b"User-agent: *\nAllow: /\nSitemap: https://example.com/sitemap.txt\n",time.time())
        if url.endswith("/sitemap.txt"):
            return FetchResponse(url,200,{"content-type":"text/plain"},MAP,time.time())
        if url.endswith(("/a","/b")):
            return FetchResponse(url,200,{"content-type":"text/html"},PAGE,time.time())
        raise AssertionError("unexpected origin or path")


class CanonicalTextSitemapTests(unittest.TestCase):
    def test_robots_sitemap_discovery_reaches_real_worker(self):
        at=time.time()
        fetcher=SitemapTransport()
        run=CrawlRun.create(CrawlRequest(
            seed_urls=("https://example.com/a",),
            allowed_hosts=("example.com",),max_depth=2,max_requests=6,
            max_documents=3,max_response_bytes=4096,max_total_bytes=24576,
            discover_sitemaps=True,min_host_delay_seconds=.25,
        ),scope={"tenant_id":"tenant","owner_id":"owner"},consent={
            "consent_id":"sitemap-consent","capture_acknowledged":True,
            "source_rights_acknowledged":True,"expires_at":at+3600,
        },now=at,fetcher=fetcher)
        for offset in (1,3,5,7):
            with patch("skeleton.ai.webcrawler.operations.time.time",return_value=at+offset):
                run.run_slice(max_steps=1,max_seconds=1,authorize=lambda:None,
                    cancelled=lambda:False,on_checkpoint=lambda snap,event:None)
        snap=run.snapshot()
        self.assertIn("https://example.com/sitemap.txt",fetcher.calls)
        self.assertIn("https://example.com/b",fetcher.calls)
        # Identical HTML across two URLs is correctly content-deduplicated.
        self.assertEqual(snap["usage"]["documents"],1)
        self.assertEqual(snap["usage"]["requests"],4)
        self.assertTrue(any(e["kind"] == "duplicate" for e in snap["events"]))
        self.assertEqual(CrawlRun.from_snapshot(snap,fetcher=fetcher).snapshot(),snap)

    def test_budget_exhaustion_blocks_sitemap_additional_network_fetch(self):
        at=time.time()
        fetcher=SitemapTransport()
        run=CrawlRun.create(CrawlRequest(
            seed_urls=("https://example.com/a",),allowed_hosts=("example.com",),
            discover_sitemaps=True,max_requests=1,max_documents=3,max_depth=2,
            max_response_bytes=4096,max_total_bytes=8192,
        ),scope={"tenant_id":"t","owner_id":"o"},consent={
            "consent_id":"sitemap-consent","capture_acknowledged":True,
            "source_rights_acknowledged":True,"expires_at":at+3600,
        },now=at,fetcher=fetcher)
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",return_value=at+offset):
                run.run_slice(max_steps=1,max_seconds=1,authorize=lambda:None,
                    cancelled=lambda:False,on_checkpoint=lambda snap,event:None)
        self.assertEqual(len(fetcher.calls),1)
        self.assertEqual(run.snapshot()["state"],"budget_exhausted")


if __name__=="__main__":
    unittest.main()
