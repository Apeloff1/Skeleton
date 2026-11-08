"""Bounded OPML feed catalogs through the real authenticated Dragon frontier."""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import CrawlPolicy, FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun
from skeleton.ai.webcrawler.structured_discovery import (
    DiscoveryError, parse_structured_discovery,
)

OPML = b"""<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0"><head><title>Flight Research Feeds</title></head>
<body>
  <outline text="Aircraft">
    <outline type="rss" text="Flight articles" xmlUrl="https://example.com/feed.rss"/>
    <outline type="atom" text="Mechanics" xmlUrl="/relative.xml"/>
    <outline type="rss" text="Private" xmlUrl="http://localhost/private"/>
    <outline type="rss" xmlUrl="https://outside.example.net/forbidden"/>
    <outline type="rss" xmlUrl="https://example.com/feed.rss"/>
  </outline>
</body></opml>"""
FEED = b"""<rss><channel><item><link>https://example.com/article</link></item></channel></rss>"""
PAGE = b"<html><title>Flight Archive</title><body>Aircraft research and propulsion evidence.</body></html>"
POLICY = CrawlPolicy(allowed_hosts=frozenset({"example.com"}))


class OPMLEntryTests(unittest.TestCase):
    def parse(self, body=OPML, media="application/opml+xml", **kwargs):
        return parse_structured_discovery(
            body, media_type=media,
            document_url="https://example.com/feeds.opml",
            policy=POLICY, **kwargs,
        )

    def test_nested_opml_discovers_only_admitted_absolute_feed_urls(self):
        outcome = self.parse()
        self.assertEqual(outcome.kind, "opml_outline")
        self.assertEqual(outcome.links, ("https://example.com/feed.rss",))
        self.assertEqual(outcome.examined_entries, 5)
        self.assertEqual(outcome.discarded_entries, 4)
        self.assertFalse(outcome.new_authority_granted)
        self.assertFalse(outcome.source_text_retained)

    def test_known_text_x_opml_is_supported(self):
        row = self.parse(media="text/x-opml")
        self.assertEqual(row.links, ("https://example.com/feed.rss",))

    def test_no_automatic_html_url_or_untagged_outlines(self):
        body = b"""<opml version="2.0"><body>
        <outline text="HTML" xmlUrl="https://example.com/page"/>
        <outline type="html" xmlUrl="https://example.com/page"/>
        </body></opml>"""
        self.assertEqual(self.parse(body).links, ())

    def test_xml_external_entities_are_refused(self):
        body = b'<!DOCTYPE opml [<!ENTITY x SYSTEM "file:///etc/passwd">]><opml><body><outline type="rss" xmlUrl="&x;"/></body></opml>'
        with self.assertRaises(DiscoveryError):
            self.parse(body)

    def test_max_links_and_entries_cannot_be_bypassed(self):
        body = (
            b'<opml version="2.0"><body>'
            + b"".join(
                f'<outline type="rss" xmlUrl="https://example.com/feed{i}.rss"/>'.encode()
                for i in range(20)
            ) + b"</body></opml>"
        )
        row = self.parse(body, max_links=3)
        self.assertTrue(row.capped)
        self.assertEqual(len(row.links), 3)
        row = self.parse(body, max_entries=4)
        self.assertTrue(row.capped)
        self.assertEqual(len(row.links), 4)

    def test_relative_feed_hint_is_rejected_not_joined(self):
        row = self.parse(b'<opml><body><outline type="rss" xmlUrl="/feed.rss"/></body></opml>')
        self.assertEqual(row.links, ())
        self.assertEqual(row.discarded_entries, 1)


class FeedCatalogFetcher:
    timeout_seconds = 3
    transport_mode = "strict_scripted_opml_catalog"

    def __init__(self):
        self.calls = []

    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        responses = {
            "https://example.com/robots.txt": ("text/plain", b"User-agent: *\nAllow: /\n"),
            "https://example.com/feeds.opml": ("application/opml+xml", OPML),
            "https://example.com/feed.rss": ("application/rss+xml", FEED),
            "https://example.com/article": ("text/html", PAGE),
        }
        if url not in responses:
            raise AssertionError("unexpected unadmitted network destination")
        mime, body = responses[url]
        if len(body) > max_bytes:
            raise AssertionError("response exceeds reserved byte ceiling")
        return FetchResponse(url, 200, {"content-type": mime}, body, time.time())


class LiveOPMLDiscoveryTests(unittest.TestCase):
    def test_nested_feed_catalog_reaches_real_worker_and_article(self):
        at = time.time()
        fetcher = FeedCatalogFetcher()
        run = CrawlRun.create(
            CrawlRequest(
                seed_urls=("https://example.com/feeds.opml",),
                allowed_hosts=("example.com",),
                max_depth=2, max_requests=5, max_documents=2,
                max_response_bytes=4096, max_total_bytes=20480,
                min_host_delay_seconds=.25,
            ),
            scope={"tenant_id": "tenant", "owner_id": "owner"},
            consent={
                "consent_id": "opml-catalog-consent",
                "capture_acknowledged": True,
                "source_rights_acknowledged": True,
                "expires_at": at + 3600,
            }, now=at, fetcher=fetcher,
        )
        for offset in (1, 3, 5, 7):
            with patch("skeleton.ai.webcrawler.operations.time.time",
                       return_value=at + offset):
                run.run_slice(
                    max_steps=1, max_seconds=1,
                    authorize=lambda: None, cancelled=lambda: False,
                    on_checkpoint=lambda snapshot, event: None,
                )
        snap = run.snapshot()
        self.assertEqual(fetcher.calls, [
            "https://example.com/robots.txt",
            "https://example.com/feeds.opml",
            "https://example.com/feed.rss",
            "https://example.com/article",
        ])
        self.assertEqual(snap["usage"]["requests"], 4)
        self.assertEqual(snap["usage"]["documents"], 1)
        self.assertTrue(run.search("propulsion")["hits"])
        self.assertEqual(CrawlRun.from_snapshot(snap, fetcher=fetcher).snapshot(), snap)


if __name__ == "__main__":
    unittest.main()
