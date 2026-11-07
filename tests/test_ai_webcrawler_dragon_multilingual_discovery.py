"""Language alternatives and bidirectional pagination through canonical admission."""
from __future__ import annotations
import time
import unittest
from unittest.mock import patch
from skeleton.ai.webcrawler.core import CrawlPolicy, FetchResponse, extract_document
from skeleton.ai.webcrawler.discovery_relations import admissible_language, navigational_relation
from skeleton.ai.webcrawler.structured_discovery import parse_structured_discovery
from skeleton.ai.webcrawler.link_header_discovery import parse_link_headers
from skeleton.ai.webcrawler.operations import CrawlRun, CrawlRequest

POLICY = CrawlPolicy(allowed_hosts=frozenset({"example.com"}))
SITEMAP = b'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
 <url><loc>https://example.com/en/article</loc>
  <xhtml:link rel="alternate" hreflang="fr" href="https://example.com/fr/article"/>
  <xhtml:link rel="alternate" hreflang="zh-Hant-TW" href="https://example.com/zh/article"/>
  <xhtml:link rel="alternate" hreflang="x-default" href="https://example.com/article"/>
  <xhtml:link rel="alternate" hreflang="no**" href="https://example.com/invalid"/>
  <xhtml:link rel="alternate" hreflang="es" href="https://outside.example.net/private"/>
  <xhtml:link rel="nofollow" hreflang="de" href="https://example.com/nofollow"/>
 </url>
</urlset>'''
HTML = b'''<!doctype html><html><head><title>Flight physics</title>
<link rel="alternate" hreflang="fr" href="/fr/article"/>
<link rel="alternate" hreflang="x-default" href="/article"/>
<link rel="alternate" hreflang="bad**" href="/bad"/>
<link rel="prev" href="/archive/page-2"/>
<link rel="alternate" type="application/rss+xml" href="/feed.xml"/>
</head><body><main><p>Aircraft stability and wing loading.</p>
<a href="/next-research">Next experiment</a>
<a rel="nofollow" href="/private">Denied follower</a></main></body></html>'''


class LanguageRelationTests(unittest.TestCase):
    def test_language_syntax_and_unknown_relations(self):
        for tag in ("en", "de-CH", "zh-Hant-TW", "x-default"):
            self.assertTrue(admissible_language(tag))
        for tag in ("", "bad**", "en_us", "a" * 64):
            self.assertFalse(admissible_language(tag))
        self.assertFalse(navigational_relation({"preload"}))
        self.assertFalse(navigational_relation({"alternate"}))
        self.assertFalse(navigational_relation({"alternate"}, hreflang="bad**"))
        self.assertTrue(navigational_relation({"alternate"}, hreflang="fr"))
        self.assertTrue(navigational_relation({"next"}))
        self.assertTrue(navigational_relation({"prev"}))

    def test_sitemap_language_alternates_not_cross_host(self):
        row = parse_structured_discovery(
            SITEMAP, media_type="application/xml",
            document_url="https://example.com/sitemap.xml", policy=POLICY,
        )
        self.assertEqual(row.kind, "sitemap_urlset")
        self.assertEqual(set(row.links), {
            "https://example.com/en/article",
            "https://example.com/fr/article",
            "https://example.com/zh/article",
            "https://example.com/article",
        })

    def test_http_link_previous_page_and_hreflang(self):
        row = parse_link_headers(
            {"link": ('</archive/2>; rel=prev, '
                      '</fr/article>; rel=alternate; hreflang="fr", '
                      '</inert>; rel=alternate; hreflang="xx**", '
                      '<https://outside.example.net/x>; rel=prev')},
            base_url="https://example.com/en/article", policy=POLICY,
        )
        self.assertEqual(row.links, (
            "https://example.com/archive/2",
            "https://example.com/fr/article",
        ))

    def test_html_relations_and_nofollow(self):
        resp = FetchResponse(
            "https://example.com/en/article", 200,
            {"content-type": "text/html"}, HTML, time.time(),
        )
        doc = extract_document(resp, resp.url)
        self.assertEqual(set(doc.links), {
            "https://example.com/fr/article",
            "https://example.com/article",
            "https://example.com/archive/page-2",
            "https://example.com/feed.xml",
            "https://example.com/next-research",
        })


class ScriptedLanguageTransport:
    timeout_seconds = 4
    transport_mode = "scripted_language_alternates"
    def __init__(self):
        self.calls = []
    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        if url == "https://example.com/robots.txt":
            return FetchResponse(url, 200, {"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n", time.time())
        if url == "https://example.com/sitemap.xml":
            return FetchResponse(url, 200, {"content-type":"application/xml"},
                                 SITEMAP, time.time())
        raise AssertionError("unexpected request from language hints")


class CanonicalMultilingualTests(unittest.TestCase):
    def test_language_hints_enter_canonical_frontier_only(self):
        now = time.time()
        fetcher = ScriptedLanguageTransport()
        run = CrawlRun.create(
            CrawlRequest(
                seed_urls=("https://example.com/sitemap.xml",),
                allowed_hosts=("example.com",), max_depth=1,
                max_requests=10, max_documents=4,
                max_response_bytes=65536, max_total_bytes=131072,
            ),
            scope={"tenant_id":"tenant", "owner_id":"owner"},
            consent={"consent_id":"language-consent",
                     "capture_acknowledged":True,
                     "source_rights_acknowledged":True,
                     "expires_at":now+3600},
            now=now, fetcher=fetcher,
        )
        for offset in (1, 3):
            with patch("skeleton.ai.webcrawler.operations.time.time",
                       return_value=now+offset):
                run.run_slice(
                    max_steps=1, max_seconds=1,
                    authorize=lambda:None, cancelled=lambda:False,
                    on_checkpoint=lambda snapshot,event:None,
                )
        snapshot = run.snapshot()
        self.assertEqual({x["url"] for x in snapshot["frontier"]}, {
            "https://example.com/en/article",
            "https://example.com/fr/article",
            "https://example.com/zh/article",
            "https://example.com/article",
        })
        self.assertEqual(snapshot["usage"]["requests"], 2)
        self.assertEqual(snapshot["usage"]["documents"], 0)
        self.assertEqual(len(fetcher.calls), 2)
        self.assertEqual(CrawlRun.from_snapshot(snapshot, fetcher=fetcher).snapshot(), snapshot)


if __name__ == "__main__":
    unittest.main()
