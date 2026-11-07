"""Real JSON Feed, Atom and RSS archive pagination through canonical CrawlRun.

Pagination headers and feed bodies are untrusted discovery only. The tested
worker still requires owner consent, robots, request/byte reserves, host scope,
finite depth and digest-verifiable snapshot custody before each fetch.
"""
from __future__ import annotations

import json
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import CrawlPolicy, FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun
from skeleton.ai.webcrawler.structured_discovery import parse_structured_discovery

URL = "https://example.com/feed.json"
POLICY = CrawlPolicy(allowed_hosts=frozenset({"example.com"}))
BASE = "https://jsonfeed.org/version/1.1"
ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom">
<link rel="next" href="/atom?page=2" type="application/atom+xml"/>
<entry><link rel="alternate" type="text/html" href="/article"/></entry>
</feed>"""
RSS = b"""<rss xmlns:atom="http://www.w3.org/2005/Atom"><channel>
<link>https://outside.example.net/not-pagination</link>
<atom:link rel="next" href="/rss?page=2" type="application/rss+xml"/>
<item><link>https://example.com/article</link></item>
</channel></rss>"""
PAGE = b"<html><title>Page</title><body>Flight archives and original vehicles.</body></html>"


def feed(items=(), **extra):
    return json.dumps({"version": BASE, "items": list(items), **extra}).encode()


class StructuredFeedPaginationTests(unittest.TestCase):
    def parse(self, data, media="application/feed+json", url=URL, **kwargs):
        return parse_structured_discovery(
            data, media_type=media, document_url=url, policy=POLICY, **kwargs,
        )

    def test_json_feed_next_url_is_real_discoverable_page(self):
        row = self.parse(feed(
            [{"url": "/article"}], next_url="/feed?page=2",
        ))
        self.assertEqual(row.kind, "json_feed")
        self.assertEqual(row.links, (
            "https://example.com/article", "https://example.com/feed?page=2",
        ))
        self.assertEqual(row.examined_entries, 2)
        self.assertFalse(row.new_authority_granted)

    def test_next_page_with_no_items_is_still_discoverable(self):
        row = self.parse(feed(next_url="/feed?page=2"))
        self.assertEqual(row.links, ("https://example.com/feed?page=2",))

    def test_cross_origin_next_url_is_discarded(self):
        row = self.parse(feed(next_url="https://outside.example.net/steal"))
        self.assertEqual(row.links, ())
        self.assertEqual(row.discarded_entries, 1)

    def test_self_loop_and_duplicate_feed_page_are_denied(self):
        self.assertEqual(self.parse(feed(next_url=URL)).links, ())
        row = self.parse(feed(
            [{"url": "/feed?page=2"}], next_url="/feed?page=2",
        ))
        self.assertEqual(row.links, ("https://example.com/feed?page=2",))
        self.assertEqual(row.discarded_entries, 1)

    def test_feed_next_url_does_not_override_link_cap(self):
        row = self.parse(feed(
            [{"url": "/article"}], next_url="/feed?page=2",
        ), max_links=1)
        self.assertEqual(row.links, ("https://example.com/article",))
        self.assertTrue(row.capped)

    def test_feed_next_url_respects_entry_cap(self):
        row = self.parse(feed(
            [{"url": "/article"}], next_url="/feed?page=2",
        ), max_entries=1)
        self.assertEqual(row.links, ("https://example.com/article",))
        self.assertTrue(row.capped)

    def test_invalid_next_url_is_not_interpreted_as_content(self):
        for value in ({"url": "/page"}, 42, "", "javascript:alert(1)"):
            with self.subTest(value=value):
                row = self.parse(feed(next_url=value))
                self.assertEqual(row.links, ())
                self.assertEqual(row.discarded_entries, 1)

    def test_atom_feed_next_relation_is_discovered_with_item(self):
        row = self.parse(ATOM, "application/atom+xml", "https://example.com/atom")
        self.assertEqual(row.links, (
            "https://example.com/article", "https://example.com/atom?page=2",
        ))
        self.assertEqual(row.examined_entries, 2)

    def test_rss_atom_extension_next_relation_is_discovered(self):
        row = self.parse(RSS, "application/rss+xml", "https://example.com/rss")
        self.assertEqual(row.links, (
            "https://example.com/article", "https://example.com/rss?page=2",
        ))
        self.assertFalse(row.new_authority_granted)

    def test_atom_wrong_rel_and_wrong_mime_never_enqueue(self):
        malicious = ATOM.replace(b'rel="next"', b'rel="payment"')
        row = self.parse(malicious, "application/atom+xml", "https://example.com/atom")
        self.assertEqual(row.links, ("https://example.com/article",))
        malicious = ATOM.replace(b'application/atom+xml', b'text/html')
        row = self.parse(malicious, "application/atom+xml", "https://example.com/atom")
        self.assertEqual(row.links, ("https://example.com/article",))

    def test_atom_external_next_page_cannot_expand_host_scope(self):
        malicious = ATOM.replace(b'/atom?page=2', b'https://outside.example.net/page')
        row = self.parse(malicious, "application/atom+xml", "https://example.com/atom")
        self.assertEqual(row.links, ("https://example.com/article",))
        self.assertEqual(row.discarded_entries, 1)


class FeedScriptedFetcher:
    timeout_seconds = 3
    transport_mode = "scripted_real_crawl_feed_pagination"

    def __init__(self):
        self.calls = []
        self.replies = {
            "https://example.com/robots.txt": (
                "text/plain", b"User-agent: *\nAllow: /\n",
            ),
            URL: (
                "application/feed+json", feed(next_url="/feed?page=2"),
            ),
            "https://example.com/feed?page=2": (
                "application/feed+json", feed([{"url": "/article"}]),
            ),
            "https://example.com/article": ("text/html", PAGE),
        }

    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        media, body = self.replies[url]
        if len(body) > max_bytes:
            raise AssertionError("scripted transport exceeded actual reservation")
        return FetchResponse(url, 200, {"content-type": media}, body, time.time())


class CanonicalFeedPagingTests(unittest.TestCase):
    def setUp(self):
        self.now = time.time()
        self.fetcher = FeedScriptedFetcher()

    def create(self, max_requests=6, max_depth=2):
        request = CrawlRequest(
            seed_urls=(URL,), allowed_hosts=("example.com",),
            max_depth=max_depth, max_requests=max_requests,
            max_documents=3, max_response_bytes=4096,
            max_total_bytes=16384, min_host_delay_seconds=.25,
        )
        return CrawlRun.create(
            request, scope={"tenant_id": "tenant", "owner_id": "owner"},
            consent={
                "consent_id": "feed-pagination-consent",
                "capture_acknowledged": True, "source_rights_acknowledged": True,
                "expires_at": self.now + 3600,
            }, now=self.now, fetcher=self.fetcher,
        )

    def tick(self, run, offset):
        with patch("skeleton.ai.webcrawler.operations.time.time",
                   return_value=self.now + offset):
            run.run_slice(
                max_steps=1, max_seconds=1, authorize=lambda: None,
                cancelled=lambda: False, on_checkpoint=lambda snapshot, event: None,
            )

    def test_real_worker_follows_two_feed_pages_then_captures_article(self):
        run = self.create()
        for offset in (1, 3, 5, 7):
            self.tick(run, offset)
        state = run.snapshot()
        self.assertEqual(self.fetcher.calls, [
            "https://example.com/robots.txt",
            URL,
            "https://example.com/feed?page=2",
            "https://example.com/article",
        ])
        self.assertEqual(state["usage"]["requests"], 4)
        self.assertEqual(state["usage"]["documents"], 1)
        self.assertEqual(next(iter(state["sources"].values()))["review_state"], "unreviewed")
        self.assertTrue(run.search("flight")["hits"])
        self.assertEqual(CrawlRun.from_snapshot(state, fetcher=self.fetcher).snapshot(), state)

    def test_zero_depth_cannot_fetch_discovered_next_page(self):
        run = self.create(max_depth=0)
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual(len(self.fetcher.calls), 2)
        self.assertEqual(run.snapshot()["frontier"], [])
        self.assertEqual(run.snapshot()["usage"]["documents"], 0)

    def test_budget_cap_prevents_unmetered_next_page_fetch(self):
        run = self.create(max_requests=2)
        self.tick(run, 1)
        self.tick(run, 3)
        self.tick(run, 5)
        self.assertEqual(len(self.fetcher.calls), 2)
        self.assertEqual(run.snapshot()["state"], "budget_exhausted")


if __name__ == "__main__":
    unittest.main()
