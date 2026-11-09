"""Exercise site noarchive/noindex/nofollow through real canonical crawler."""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.capture_rights import source_capture_rights
from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun

ROBOTS = b"User-agent: *\nAllow: /\n"
PAGE = b"<html><head><title>Archive</title></head><body>Aircraft physics archived <a href='/next'>more</a></body></html>"

class RightsContractTests(unittest.TestCase):
    def classify(self, markup=PAGE, extra=None, media="text/html"):
        return source_capture_rights(extra or {}, markup, media_type=media)

    def test_default_sources_are_retained_and_links_followed(self):
        d = self.classify()
        self.assertTrue(d.retain)
        self.assertTrue(d.follow)
        self.assertTrue(d.site_cannot_grant_authority)

    def test_noindex_denies_source_storage_but_allows_link_follow(self):
        d = self.classify(extra={"X-Robots-Tag": "noindex"})
        self.assertFalse(d.retain)
        self.assertTrue(d.follow)

    def test_nofollow_denies_link_schedule_but_allows_source_retention(self):
        d = self.classify(extra={"x-robots-tag": "nofollow"})
        self.assertTrue(d.retain)
        self.assertFalse(d.follow)

    def test_none_denies_both(self):
        d = self.classify(extra={"x-robots-tag": "none"})
        self.assertFalse(d.retain)
        self.assertFalse(d.follow)

    def test_noarchive_header_blocks_plain_text_and_json(self):
        for media in ("text/plain", "application/json", "text/html"):
            with self.subTest(media=media):
                d = self.classify(extra={"x-robots-tag": "noarchive"}, media=media)
                self.assertFalse(d.retain)

    def test_html_meta_name_robots_honored(self):
        html = b'<html><head><meta name="robots" content="nofollow, noarchive"></head><body>text</body></html>'
        d = self.classify(markup=html)
        self.assertFalse(d.retain)
        self.assertFalse(d.follow)
        self.assertIn("html_meta", d.source)

    def test_agent_specific_header_applies_only_to_dragon(self):
        d = self.classify(extra={"X-Robots-Tag": "Googlebot: noindex"})
        self.assertTrue(d.retain)
        d = self.classify(extra={"X-Robots-Tag": "SkeletonAI-Crawler: noindex"})
        self.assertFalse(d.retain)

    def test_overflow_fails_closed(self):
        large = b"<html>" + (b"<div>" * 25) + b"source</html>"
        d = source_capture_rights(
            {}, large, media_type="text/html", max_meta_tags=8,
        )
        self.assertFalse(d.retain)
        self.assertFalse(d.follow)

    def test_unknown_page_directive_cannot_grant_permissions(self):
        d = self.classify(extra={"X-Robots-Tag": "all, index, follow"})
        self.assertTrue(d.site_cannot_grant_authority)


class SitePolicyFetcher:
    timeout_seconds = 3
    transport_mode = "scripted_site_directives"
    def __init__(self, directives=None, meta=b"", mime="text/html"):
        self.directives, self.meta, self.mime = directives, meta, mime
        self.calls = []

    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchResponse(url, 200, {"content-type": "text/plain"}, ROBOTS, time.time())
        if url.endswith("/next"):
            return FetchResponse(url, 200, {"content-type": "text/html"}, PAGE, time.time())
        headers = {"content-type": self.mime}
        if self.directives is not None:
            headers["x-robots-tag"] = self.directives
        body = PAGE if not self.meta else self.meta
        return FetchResponse(url, 200, headers, body, time.time())


class RepeatedRobotsHeaderTests(unittest.TestCase):
    def test_repeated_site_denials_cannot_be_overwritten(self):
        from skeleton.ai.webcrawler.bound_http import _coalesce_bounded_xrobots_headers
        headers={"x-robots-tag":"index"}
        _coalesce_bounded_xrobots_headers([
            ("X-Robots-Tag","noarchive"),("X-Robots-Tag","nofollow"),
        ],headers)
        rights=source_capture_rights(headers,PAGE,media_type="text/html")
        self.assertFalse(rights.retain)
        self.assertFalse(rights.follow)

    def test_oversized_robots_metadata_denies_capture(self):
        from skeleton.ai.webcrawler.bound_http import _coalesce_bounded_xrobots_headers
        headers={}
        _coalesce_bounded_xrobots_headers([
            ("x-robots-tag","index"*1000),
            ("x-robots-tag","noarchive"),
        ],headers)
        self.assertEqual(headers["x-robots-tag"],"none")


class CanonicalSiteRightsTests(unittest.TestCase):
    def create(self, fetcher):
        at = time.time()
        request = CrawlRequest(
            seed_urls=("https://example.com/start",), allowed_hosts=("example.com",),
            max_depth=1, max_requests=5, max_documents=3,
            max_response_bytes=4096, max_total_bytes=16384,
            min_host_delay_seconds=.25,
        )
        run = CrawlRun.create(request, scope={
            "tenant_id": "t", "owner_id": "o",
        }, consent={
            "consent_id": "site-rights-optin",
            "capture_acknowledged": True,
            "source_rights_acknowledged": True,
            "expires_at": at+3600,
        }, now=at, fetcher=fetcher)
        return run, at

    def tick(self, run, at):
        with patch("skeleton.ai.webcrawler.operations.time.time", return_value=at):
            run.run_slice(max_steps=1, max_seconds=1,
                authorize=lambda:None, cancelled=lambda:False,
                on_checkpoint=lambda snap,event:None)

    def test_noindex_is_not_retained_but_eligible_discovery_continues(self):
        transport = SitePolicyFetcher(directives="noindex")
        run, at = self.create(transport)
        self.tick(run, at+1); self.tick(run, at+3)
        snap=run.snapshot()
        self.assertEqual(snap["usage"]["documents"],0)
        self.assertIn("https://example.com/next", [x["url"] for x in snap["frontier"]])
        self.assertEqual(snap["events"][-1]["kind"],"source_rights_restricted")
        self.assertEqual(CrawlRun.from_snapshot(snap,fetcher=transport).snapshot(),snap)

    def test_nofollow_blocks_all_document_links(self):
        transport = SitePolicyFetcher(directives="nofollow")
        run, at=self.create(transport)
        self.tick(run, at+1);self.tick(run,at+3)
        snap=run.snapshot()
        self.assertEqual(snap["usage"]["documents"],1)
        self.assertEqual(snap["frontier"],[])
        self.assertEqual(len(transport.calls),2)

    def test_noarchive_does_not_retain_source_text(self):
        transport=SitePolicyFetcher(directives="noarchive")
        run,at=self.create(transport)
        self.tick(run,at+1);self.tick(run,at+3)
        self.assertEqual(run.snapshot()["usage"]["documents"],0)
        self.assertFalse(run.search("aircraft")["hits"])

    def test_meta_robots_none_denies_capture_and_follow(self):
        content=b'<html><head><meta name="robots" content="none"></head><body><a href="/next">text</a></body></html>'
        transport=SitePolicyFetcher(meta=content)
        run,at=self.create(transport)
        self.tick(run,at+1);self.tick(run,at+3)
        self.assertEqual(run.snapshot()["usage"]["documents"],0)
        self.assertEqual(run.snapshot()["frontier"],[])
        self.assertEqual(len(transport.calls),2)

    def test_open_default_page_retains_and_follows(self):
        transport=SitePolicyFetcher()
        run,at=self.create(transport)
        self.tick(run,at+1);self.tick(run,at+3)
        self.assertEqual(run.snapshot()["usage"]["documents"],1)
        self.assertEqual([x["url"] for x in run.snapshot()["frontier"]],
            ["https://example.com/next"])


if __name__=="__main__":
    unittest.main()
