"""Production Dragon crawler sitemap/feed discovery and metered-fetch regressions.

These tests exercise the *real* CrawlRun.run_slice and robots/host/cumulative
budget machinery with a scripted in-memory transport. They intentionally do
not issue a real network request or connect to Mongo. Parser tests validate
bounded, untrusted XML discovery and gzip decompression safety.
"""
from __future__ import annotations

from copy import deepcopy
import gzip
import json
import time
from unittest.mock import patch
import unittest

from skeleton.ai.webcrawler.core import CrawlPolicy, FetchResponse
from skeleton.ai.webcrawler.operations import (
    CrawlOperationError, CrawlRequest, CrawlRun,
)
from skeleton.ai.webcrawler.structured_discovery import (
    DiscoveryError, parse_structured_discovery, extract_robots_sitemaps,
    parse_json_feed,
)


SITEMAP = b'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://example.com/article-a</loc></url>
<url><loc>https://example.com/article-b</loc></url>
<url><loc>https://outside.example.net/private</loc></url>
<url><loc>http://localhost/private</loc></url>
<url><loc>https://example.com/article-a</loc></url>
</urlset>'''
INDEX = b'''<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://example.com/articles.xml</loc></sitemap>
<sitemap><loc>https://example.com/articles.xml.gz</loc></sitemap>
<sitemap><loc>https://example.com/evil.html</loc></sitemap>
<sitemap><loc>https://outside.example.net/evil.xml</loc></sitemap>
</sitemapindex>'''
RSS = b'''<rss version="2.0"><channel><title>Articles</title>
<item><link>https://example.com/rss-article</link></item>
<item><link>https://evil.example.net/rss-article</link></item>
</channel></rss>'''
ATOM = b'''<feed xmlns="http://www.w3.org/2005/Atom">
<entry><link href="https://example.com/atom-article" rel="alternate"
type="text/html"/></entry>
<entry><link href="https://example.com/download.zip" rel="enclosure"/></entry>
</feed>'''
ROBOTS = b"User-agent: *\nAllow: /\nSitemap: https://example.com/sitemap.xml\n"
HTML = b"<html><head><title>Article</title></head><body>Archive capture methodology explains the recorded methods in detail.</body></html>"
JSONFEED = json.dumps({
    "version": "https://jsonfeed.org/version/1.1",
    "title": "Structured captured posts",
    "items": [
        {"id": "one", "url": "https://example.com/article-a",
         "content_html": "<script>Untrusted instructions are never retained as capture</script>"},
        {"id": "two", "url": "https://outside.example.net/blocked"},
        {"id": "three", "url": "https://example.com/article-a"},
        {"id": "four", "external_url": "/article-b"},
    ],
}).encode()
HTML_WITH_DISCOVERY_LINKS = b"""<html><head><title>Index</title>
<link rel="next" href="/page-two">
<link rel="alternate" type="application/rss+xml" href="/feed.rss">
<link rel="alternate" type="application/feed+json" href="/feed.json">
<link rel="icon" href="https://outside.example.net/evil.ico">
</head><body>Archive capture methodology with substantial article evidence.</body></html>"""


class ScriptedFetcher:
    timeout_seconds = 10.0
    transport_mode = "scripted_authoritative_worker_test"

    def __init__(self, replies):
        self.replies = dict(replies)
        self.calls = []

    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append((url, user_agent, max_bytes))
        if url not in self.replies:
            raise AssertionError("unrequested or unregistered network destination")
        status, media_type, body = self.replies[url]
        if len(body) > max_bytes:
            raise AssertionError("test response over pre-reserved response cap")
        return FetchResponse(
            url=url, status=status, headers={"content-type": media_type},
            body=body, fetched_at=time.time(),
        )


class StructuredParserTests(unittest.TestCase):
    def setUp(self):
        self.policy = CrawlPolicy(allowed_hosts=frozenset({"example.com"}))
        self.site = "https://example.com/sitemap.xml"

    def parse(self, body=SITEMAP, media="application/xml", url=None, **options):
        return parse_structured_discovery(
            body, media_type=media, document_url=url or self.site,
            policy=self.policy, **options,
        )

    def test_sitemap_captures_only_allowlisted_unique_urls(self):
        result = self.parse()
        self.assertEqual(result.kind, "sitemap_urlset")
        self.assertEqual(result.links, (
            "https://example.com/article-a",
            "https://example.com/article-b",
        ))
        self.assertEqual(result.examined_entries, 5)
        self.assertEqual(result.discarded_entries, 3)
        self.assertFalse(result.source_text_retained)
        self.assertFalse(result.new_authority_granted)

    def test_sitemap_index_only_discovers_sub_sitemaps(self):
        result = self.parse(INDEX)
        self.assertEqual(result.kind, "sitemap_index")
        self.assertEqual(result.links, (
            "https://example.com/articles.xml",
            "https://example.com/articles.xml.gz",
        ))

    def test_rss_article_links_are_discovered(self):
        result = self.parse(RSS, "application/rss+xml", url="https://example.com/feed.rss")
        self.assertEqual(result.kind, "rss_feed")
        self.assertEqual(result.links, ("https://example.com/rss-article",))

    def test_atom_alternate_links_are_discovered(self):
        result = self.parse(ATOM, "application/atom+xml",
                            url="https://example.com/feed.atom")
        self.assertEqual(result.kind, "atom_feed")
        self.assertEqual(result.links, ("https://example.com/atom-article",))

    def test_atom_relative_links_remain_same_host(self):
        body = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><link href="/relative" /></entry></feed>'
        result = self.parse(body, "application/atom+xml")
        self.assertEqual(result.links, ("https://example.com/relative",))

    def test_xml_sitemap_utf8_declaration_is_accepted(self):
        result = self.parse()
        self.assertEqual(result.kind, "sitemap_urlset")

    def test_xml_doctype_is_rejected_before_parser(self):
        with self.assertRaises(DiscoveryError):
            self.parse(b'<!DOCTYPE urlset [<!ENTITY x "boom">]><urlset>&x;</urlset>')

    def test_billion_laughs_style_entities_are_never_expanded(self):
        attack = b'<!DOCTYPE r [<!ENTITY a "1234567890"><!ENTITY b "&a;&a;&a;">]><urlset>&b;</urlset>'
        with self.assertRaises(DiscoveryError):
            self.parse(attack)

    def test_utf16_or_nul_xml_is_rejected(self):
        with self.assertRaises(DiscoveryError):
            self.parse(SITEMAP.decode().encode("utf-16"))
        with self.assertRaises(DiscoveryError):
            self.parse(b"<urlset>\x00</urlset>")

    def test_xml_parser_rejects_malformed_document(self):
        with self.assertRaises(DiscoveryError):
            self.parse(b"<urlset><url><loc>oops</urlset>")

    def test_unknown_xml_root_is_not_a_sitemap(self):
        with self.assertRaises(DiscoveryError):
            self.parse(b"<arbitrary><loc>https://example.com/evil</loc></arbitrary>")

    def test_sitemap_rejects_relative_locations(self):
        result = self.parse(b"<urlset><url><loc>/unsafe</loc></url></urlset>")
        self.assertEqual(result.links, ())
        self.assertEqual(result.discarded_entries, 1)

    def test_unsafe_credentials_and_private_destinations_are_rejected(self):
        body = b"<urlset><url><loc>https://user:secret@example.com/private</loc></url><url><loc>http://127.0.0.1/private</loc></url></urlset>"
        self.assertEqual(self.parse(body).links, ())

    def test_feed_media_type_does_not_override_host_scope(self):
        result = self.parse(RSS, "application/rss+xml", url="https://example.com/feed.rss")
        self.assertEqual(len(result.links), 1)

    def test_gzip_sitemap_uses_bounded_inflate(self):
        url = "https://example.com/sitemap.xml.gz"
        result = self.parse(gzip.compress(SITEMAP), "application/gzip", url=url)
        self.assertEqual(result.links[0], "https://example.com/article-a")

    def test_gzip_disallowed_outside_xml_gz_path(self):
        with self.assertRaises(DiscoveryError):
            self.parse(gzip.compress(SITEMAP), "application/gzip", url=self.site)

    def test_gzip_bomb_is_rejected_at_output_bound(self):
        bomb = gzip.compress(b"<urlset>" + b"A" * 1_100_000 + b"</urlset>")
        with self.assertRaises(DiscoveryError):
            self.parse(bomb, "application/x-gzip",
                       url="https://example.com/sitemap.xml.gz")

    def test_truncated_gzip_is_rejected(self):
        with self.assertRaises(DiscoveryError):
            self.parse(gzip.compress(SITEMAP)[:-7], "application/gzip",
                       url="https://example.com/sitemap.xml.gz")

    def test_content_length_limit_is_fail_closed(self):
        with self.assertRaises(DiscoveryError):
            self.parse(b"A" * (1_048_576 + 1))

    def test_nested_xml_oversize_is_fail_closed(self):
        payload = b"<urlset>" + b"<nest>" * 50 + b"</nest>" * 50 + b"</urlset>"
        with self.assertRaises(DiscoveryError):
            self.parse(payload)

    def test_max_link_limit_is_bounded_without_spawning_work(self):
        body = b"<urlset>" + b"".join(
            ("<url><loc>https://example.com/p%d</loc></url>" % i).encode()
            for i in range(20)
        ) + b"</urlset>"
        result = self.parse(body, max_links=4)
        self.assertEqual(len(result.links), 4)
        self.assertTrue(result.capped)

    def test_max_entry_limit_is_hard_bounded(self):
        body = b"<urlset>" + b"".join(
            ("<url><loc>https://example.com/p%d</loc></url>" % i).encode()
            for i in range(15)
        ) + b"</urlset>"
        result = self.parse(body, max_entries=3)
        self.assertEqual(len(result.links), 3)
        self.assertTrue(result.capped)

    def test_zero_link_limit_fails(self):
        with self.assertRaises(ValueError):
            self.parse(max_links=0)

    def test_crawler_scope_cannot_be_rebound_by_document_url(self):
        with self.assertRaises(DiscoveryError):
            self.parse(SITEMAP, url="https://outside.example.net/sitemap.xml")

    def test_robots_sitemaps_must_be_same_origin_and_xml(self):
        directives = ("User-agent: *\nSitemap: https://example.com/sitemap.xml\n"
                      "Sitemap: https://outside.example.net/evil.xml\n"
                      "Sitemap: http://example.com/downgrade.xml\n"
                      "Sitemap: https://example.com/payload.exe\n"
                      "Sitemap: https://example.com/sitemap.xml")
        self.assertEqual(
            extract_robots_sitemaps(
                directives, origin="https://example.com", policy=self.policy,
            ), ("https://example.com/sitemap.xml",),
        )

    def test_robots_sitemaps_bounded_by_eight(self):
        directives = "Sitemap: " + "\nSitemap: ".join(
            "https://example.com/s%d.xml" % i for i in range(20)
        )
        self.assertEqual(len(extract_robots_sitemaps(
            directives, origin="https://example.com",
            policy=self.policy,
        )), 8)


    def test_json_feed_v1_1_discovers_item_urls_without_content(self):
        result = parse_json_feed(
            JSONFEED, document_url="https://example.com/feed.json",
            policy=self.policy,
        )
        self.assertEqual(result.kind, "json_feed")
        self.assertEqual(result.links, (
            "https://example.com/article-a",
            "https://example.com/article-b",
        ))
        self.assertEqual(result.examined_entries, 4)
        self.assertEqual(result.discarded_entries, 2)
        self.assertNotIn("Untrusted instructions", repr(result))

    def test_json_feed_application_json_dispatch_is_supported(self):
        result = self.parse(
            JSONFEED, "application/json",
            url="https://example.com/feed.json",
        )
        self.assertEqual(result.kind, "json_feed")
        self.assertEqual(len(result.links), 2)

    def test_json_feed_v1_is_supported(self):
        body = JSONFEED.replace(b"version/1.1", b"version/1")
        result = parse_json_feed(body, document_url="https://example.com/feed.json",
                                 policy=self.policy)
        self.assertEqual(result.kind, "json_feed")

    def test_json_feed_rejects_missing_version(self):
        with self.assertRaises(DiscoveryError):
            parse_json_feed(
                b'{"items":[]}', document_url="https://example.com/feed.json",
                policy=self.policy,
            )

    def test_json_feed_rejects_duplicate_keys(self):
        with self.assertRaises(DiscoveryError):
            parse_json_feed(
                b'{"version":"https://jsonfeed.org/version/1","version":"attack","items":[]}',
                document_url="https://example.com/feed.json", policy=self.policy,
            )

    def test_json_feed_rejects_nonfinite_literals(self):
        with self.assertRaises(DiscoveryError):
            parse_json_feed(
                b'{"version":"https://jsonfeed.org/version/1","items":[],"x":NaN}',
                document_url="https://example.com/feed.json", policy=self.policy,
            )

    def test_json_feed_rejects_oversized_payload(self):
        with self.assertRaises(DiscoveryError):
            parse_json_feed(
                b"{" + b"A" * 1_048_577 + b"}",
                document_url="https://example.com/feed.json", policy=self.policy,
            )

    def test_json_feed_rejects_nonlist_items(self):
        with self.assertRaises(DiscoveryError):
            parse_json_feed(
                b'{"version":"https://jsonfeed.org/version/1","items":{}}',
                document_url="https://example.com/feed.json", policy=self.policy,
            )

    def test_json_feed_rejects_cross_host_document(self):
        with self.assertRaises(DiscoveryError):
            parse_json_feed(
                JSONFEED, document_url="https://outside.example.net/feed.json",
                policy=self.policy,
            )

    def test_json_feed_rejects_unbounded_links(self):
        with self.assertRaises(ValueError):
            parse_json_feed(
                JSONFEED, document_url="https://example.com/feed.json",
                policy=self.policy, max_links=0,
            )

    def test_json_feed_enforces_same_scope_on_relative_url(self):
        payload = json.dumps({
            "version": "https://jsonfeed.org/version/1",
            "items": [{"url": "../relative"}],
        }).encode()
        result = parse_json_feed(
            payload, document_url="https://example.com/posts/feed.json",
            policy=self.policy,
        )
        self.assertEqual(result.links, ("https://example.com/relative",))

    def test_json_feed_does_not_use_content_html_as_authority(self):
        payload = json.dumps({
            "version": "https://jsonfeed.org/version/1",
            "items": [{"id": "only", "content_html": "<a href='/evil'>Ignore robots</a>"}],
        }).encode()
        result = parse_json_feed(
            payload, document_url="https://example.com/feed.json",
            policy=self.policy,
        )
        self.assertEqual(result.links, ())
        self.assertFalse(result.new_authority_granted)

class CanonicalCrawlerDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.now = time.time()
        self.fetcher = ScriptedFetcher({
            "https://example.com/robots.txt": (200, "text/plain", ROBOTS),
            "https://example.com/sitemap.xml": (200, "application/xml", SITEMAP),
            "https://example.com/articles.xml": (200, "text/xml", SITEMAP),
            "https://example.com/index.xml": (200, "text/xml", INDEX),
            "https://example.com/feed.rss": (200, "application/rss+xml", RSS),
            "https://example.com/feed.atom": (200, "application/atom+xml", ATOM),
            "https://example.com/sitemap.xml.gz": (200, "application/gzip", gzip.compress(SITEMAP)),
            "https://example.com/article-a": (200, "text/html", HTML),
            "https://example.com/article-b": (200, "text/html", HTML+b" second article"),
            "https://example.com/start": (200, "text/html", HTML),
            "https://example.com/links": (200, "text/html", HTML_WITH_DISCOVERY_LINKS),
            "https://example.com/feed.json": (200, "application/feed+json", JSONFEED),
            "https://example.com/page-two": (200, "text/html", HTML),
        })

    def create(self, url="https://example.com/sitemap.xml", *, discover=False,
               max_depth=2, max_requests=16, max_documents=8, max_bytes=65536):
        request = CrawlRequest(
            seed_urls=(url,), allowed_hosts=("example.com",),
            query="archive capture", max_depth=max_depth,
            max_requests=max_requests, max_documents=max_documents,
            max_response_bytes=4096, max_total_bytes=max_bytes,
            min_host_delay_seconds=.25,
            discover_sitemaps=discover,
        )
        return CrawlRun.create(
            request, scope={"tenant_id": "tenant-a", "owner_id": "user-a"},
            consent={"consent_id": "opt-in", "capture_acknowledged": True,
                     "source_rights_acknowledged": True,
                     "expires_at": self.now + 3600},
            now=self.now, fetcher=self.fetcher,
        )

    def tick(self, run, offset, *, max_steps=1):
        with patch("skeleton.ai.webcrawler.operations.time.time",
                   return_value=self.now + offset):
            return run.run_slice(
                max_steps=max_steps, max_seconds=1,
                authorize=lambda: None, cancelled=lambda: False,
                on_checkpoint=lambda snapshot, event: None,
            )

    def test_live_worker_fetches_robots_before_sitemap(self):
        run = self.create()
        self.tick(run, 1)
        self.assertEqual(len(self.fetcher.calls), 1)
        self.assertEqual(self.fetcher.calls[0][0], "https://example.com/robots.txt")
        self.assertEqual(run.snapshot()["usage"]["requests"], 1)
        self.assertEqual(run.snapshot()["usage"]["documents"], 0)

    def test_sitemap_discovery_enqueues_only_consented_hosts(self):
        run = self.create()
        self.tick(run, 1)
        self.tick(run, 3)
        state = run.snapshot()
        self.assertEqual(state["usage"]["requests"], 2)
        self.assertEqual(state["usage"]["documents"], 0)
        self.assertEqual(
            {x["url"] for x in state["frontier"]},
            {"https://example.com/article-a", "https://example.com/article-b"},
        )
        self.assertEqual(state["events"][-1]["kind"], "discovered")
        self.assertEqual(state["events"][-1]["reason"],
                         "sitemap_urlset:2_frontier_links_admitted")
        CrawlRun.from_snapshot(state, fetcher=self.fetcher)

    def test_discovered_article_is_captured_by_real_worker(self):
        run = self.create()
        self.tick(run, 1)
        self.tick(run, 3)
        self.tick(run, 5)
        state = run.snapshot()
        self.assertEqual(state["usage"]["requests"], 3)
        self.assertEqual(state["usage"]["documents"], 1)
        self.assertEqual(len(state["sources"]), 1)
        source = next(iter(state["sources"].values()))
        self.assertEqual(source["review_state"], "unreviewed")
        self.assertEqual(source["provenance"]["training_permission"], False)
        self.assertEqual(source["provenance"]["raw_bytes_retained"], False)
        self.assertTrue(source["text"])
        CrawlRun.from_snapshot(state, fetcher=self.fetcher)

    def test_feed_discovery_uses_same_canonical_worker(self):
        run = self.create(url="https://example.com/feed.rss")
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual(
            [x["url"] for x in run.snapshot()["frontier"]],
            ["https://example.com/rss-article"],
        )
        self.assertEqual(run.snapshot()["events"][-1]["kind"], "discovered")

    def test_sitemap_index_can_queue_nested_index_targets(self):
        run = self.create(url="https://example.com/index.xml", max_depth=2)
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertIn("https://example.com/articles.xml",
                      [x["url"] for x in run.snapshot()["frontier"]])
        self.assertNotIn("https://example.com/evil.html",
                         [x["url"] for x in run.snapshot()["frontier"]])

    def test_gzip_sitemap_is_discovered_with_metered_reservation(self):
        run = self.create(url="https://example.com/sitemap.xml.gz")
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual(run.snapshot()["events"][-1]["kind"], "discovered")
        self.assertEqual(run.snapshot()["usage"]["requests"], 2)

    def test_opt_in_robots_sitemap_enqueues_new_root(self):
        run = self.create(url="https://example.com/start", discover=True)
        self.tick(run, 1)
        self.assertIn("https://example.com/sitemap.xml",
                      [x["url"] for x in run.snapshot()["frontier"]])
        self.assertEqual(run.snapshot()["usage"]["documents"], 0)

    def test_default_robots_sitemap_discovery_is_off(self):
        run = self.create(url="https://example.com/start", discover=False)
        self.tick(run, 1)
        self.assertNotIn("https://example.com/sitemap.xml",
                         [x["url"] for x in run.snapshot()["frontier"]])

    def test_manually_seeded_sitemap_respects_zero_depth_limit(self):
        run = self.create(max_depth=0)
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual(run.snapshot()["frontier"], [])
        self.assertEqual(run.snapshot()["usage"]["documents"], 0)
        self.assertEqual(run.snapshot()["state"], "completed")

    def test_json_feed_is_fetched_and_article_urls_queued(self):
        run = self.create(url="https://example.com/feed.json")
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual(
            {x["url"] for x in run.snapshot()["frontier"]},
            {"https://example.com/article-a", "https://example.com/article-b"},
        )
        self.assertEqual(run.snapshot()["events"][-1]["kind"], "discovered")
        self.assertEqual(run.snapshot()["usage"]["documents"], 0)

    def test_html_link_next_and_feed_discovery_reach_real_frontier(self):
        run = self.create(url="https://example.com/links", max_depth=2)
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual(
            {x["url"] for x in run.snapshot()["frontier"]},
            {"https://example.com/page-two", "https://example.com/feed.rss",
             "https://example.com/feed.json"},
        )
        self.assertNotIn("https://outside.example.net/evil.ico",
                         [x["url"] for x in run.snapshot()["frontier"]])

    def test_json_feed_cannot_exceed_canonical_request_budget(self):
        run = self.create(url="https://example.com/feed.json", max_requests=1)
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual(len(self.fetcher.calls), 1)
        self.assertEqual(run.snapshot()["state"], "budget_exhausted")

    def test_feed_discovery_is_not_counted_as_a_captured_document(self):
        run = self.create(url="https://example.com/feed.json", max_depth=0)
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual(run.snapshot()["usage"]["documents"], 0)
        self.assertEqual(run.snapshot()["usage"]["requests"], 2)
        self.assertEqual(run.snapshot()["state"], "completed")

    def test_request_rejects_non_boolean_sitemap_opt_in(self):
        with self.assertRaises(CrawlOperationError):
            CrawlRequest(
                seed_urls=("https://example.com/",),
                allowed_hosts=("example.com",),
                discover_sitemaps=1,
            )

    def test_xml_discovery_never_mints_training_or_publication_grant(self):
        run = self.create()
        self.tick(run, 1)
        self.tick(run, 3)
        snapshot = run.snapshot()
        self.assertFalse(any("publication" in e.get("reason", "")
                             for e in snapshot["events"]))
        self.assertEqual(snapshot["usage"]["documents"], 0)

    def test_robots_disallow_prevents_followup_sitemap_request(self):
        self.fetcher.replies["https://example.com/robots.txt"] = (
            200, "text/plain", b"User-agent: *\nDisallow: /"
        )
        run = self.create()
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual(len(self.fetcher.calls), 1)
        self.assertTrue(any(x["kind"] == "rejected"
                            for x in run.snapshot()["events"]))

    def test_request_budget_exhaustion_prevents_unmetered_sitemap_fetch(self):
        run = self.create(max_requests=1)
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual(len(self.fetcher.calls), 1)
        self.assertEqual(run.snapshot()["usage"]["requests"], 1)
        self.assertEqual(run.snapshot()["state"], "budget_exhausted")

    def test_expired_consent_denies_structured_discovery(self):
        run = self.create()
        with patch("skeleton.ai.webcrawler.operations.time.time",
                   return_value=self.now + 3700):
            with self.assertRaises(CrawlOperationError):
                run.run_slice(max_steps=1, max_seconds=1)

    def test_backend_snapshot_restore_preserves_sitemap_request_option(self):
        run = self.create(discover=True)
        snapshot = run.snapshot()
        clone = CrawlRun.from_snapshot(snapshot, fetcher=self.fetcher)
        self.assertTrue(clone.request.discover_sitemaps)
        self.assertEqual(clone.snapshot(), snapshot)


if __name__ == "__main__":
    unittest.main()
