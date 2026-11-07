"""Redirect-relative links and partial-body custody in the canonical Dragon worker.

An HTTP redirect changes the base for relative navigation, not the recorded
original seed identity. Partial 206 bodies and misleading Content-Range
headers are never captured as complete research evidence.
"""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import FetchResponse, extract_document
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun

ROBOTS = b"User-agent: *\nAllow: /\n"
INDEX = b"""<html><title>Moved Flight Index</title><body>
Flight mechanics archive. <a href="chapter.html">Chapter one</a>
<a href="https://outside.example.net/blocked">Untrusted external link</a>
</body></html>"""
CHAPTER = b"<html><title>Chapter One</title><body>Archived aircraft propulsion details.</body></html>"


class StrictScriptedFetch:
    timeout_seconds = 4
    transport_mode = "scripted_redirect_source_admission"

    def __init__(self, *, partial=False, forged_range=False):
        self.partial = partial
        self.forged_range = forged_range
        self.calls: list[str] = []

    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        if url == "https://example.com/robots.txt":
            return FetchResponse(
                url, 200, {"content-type": "text/plain"}, ROBOTS, time.time(),
            )
        if url == "https://example.com/start":
            return FetchResponse(
                url, 302, {"location": "/docs/landing/index.html"}, b"", time.time(),
            )
        if url == "https://example.com/docs/landing/index.html":
            if self.partial or self.forged_range:
                headers = {"content-type": "text/html"}
                if self.forged_range:
                    headers["content-range"] = "bytes 0-50/5000"
                return FetchResponse(
                    url, 206 if self.partial else 200, headers,
                    INDEX, time.time(),
                )
            return FetchResponse(
                url, 200, {"content-type": "text/html"}, INDEX, time.time(),
            )
        if url == "https://example.com/docs/landing/chapter.html":
            return FetchResponse(
                url, 200, {"content-type": "text/html"}, CHAPTER, time.time(),
            )
        raise AssertionError(f"unexpected network request: {url}")


class RealRedirectTests(unittest.TestCase):
    def setUp(self):
        self.at = time.time()

    def make_run(self, fetcher):
        return CrawlRun.create(
            CrawlRequest(
                seed_urls=("https://example.com/start",),
                allowed_hosts=("example.com",),
                max_depth=2, max_requests=8, max_documents=4,
                max_response_bytes=4096, max_total_bytes=32768,
                min_host_delay_seconds=.25,
            ),
            scope={"tenant_id": "tenant", "owner_id": "owner"},
            consent={
                "consent_id": "redirect-consent",
                "capture_acknowledged": True,
                "source_rights_acknowledged": True,
                "expires_at": self.at + 3600,
            },
            now=self.at, fetcher=fetcher,
        )

    def step(self, run, offset):
        with patch("skeleton.ai.webcrawler.operations.time.time",
                   return_value=self.at + offset):
            run.run_slice(
                max_steps=1, max_seconds=1,
                authorize=lambda: None, cancelled=lambda: False,
                on_checkpoint=lambda snapshot, event: None,
            )

    def test_followup_links_use_final_redirect_destination(self):
        fetcher = StrictScriptedFetch()
        run = self.make_run(fetcher)
        for offset in (1, 3, 5):
            self.step(run, offset)
        state = run.snapshot()
        self.assertEqual(
            [item["url"] for item in state["frontier"]],
            ["https://example.com/docs/landing/chapter.html"],
        )
        self.assertNotIn("https://example.com/chapter.html", fetcher.calls)
        self.assertEqual(state["usage"]["documents"], 1)
        source = next(iter(state["sources"].values()))
        self.assertEqual(source["canonical_url"], "https://example.com/start")
        self.assertEqual(
            source["fetched_url"],
            "https://example.com/docs/landing/index.html",
        )
        self.step(run, 7)
        self.assertEqual(run.snapshot()["usage"]["documents"], 2)
        self.assertTrue(run.search("propulsion")["hits"])
        self.assertEqual(
            CrawlRun.from_snapshot(run.snapshot(), fetcher=fetcher).snapshot(),
            run.snapshot(),
        )

    def test_206_partial_document_does_not_capture_or_discover(self):
        fetcher = StrictScriptedFetch(partial=True)
        run = self.make_run(fetcher)
        for offset in (1, 3, 5):
            self.step(run, offset)
        state = run.snapshot()
        self.assertEqual(state["usage"]["documents"], 0)
        self.assertEqual(state["frontier"], [])
        self.assertEqual(state["events"][-1]["kind"], "rejected")
        self.assertEqual(
            state["events"][-1]["reason"], "partial_content_not_authoritative",
        )

    def test_content_range_on_http_200_fails_closed(self):
        fetcher = StrictScriptedFetch(forged_range=True)
        run = self.make_run(fetcher)
        for offset in (1, 3, 5):
            self.step(run, offset)
        self.assertEqual(run.snapshot()["usage"]["documents"], 0)
        self.assertEqual(run.snapshot()["frontier"], [])
        self.assertFalse(run.search("flight")["hits"])

    def test_direct_extractor_keeps_canonical_identity_and_final_link_base(self):
        row = extract_document(
            FetchResponse(
                "https://example.com/docs/landing/index.html", 200,
                {"content-type": "text/html"}, INDEX, self.at,
            ),
            "https://example.com/start",
            link_base_url="https://example.com/docs/landing/index.html",
        )
        self.assertEqual(row.canonical_url, "https://example.com/start")
        self.assertIn(
            "https://example.com/docs/landing/chapter.html", row.links,
        )
        self.assertIn(
            "https://outside.example.net/blocked", row.links,
        )
        # Lower-level pure extraction does not expand source scope;
        # the canonical CrawlRun frontier applies the host allowlist.


if __name__ == "__main__":
    unittest.main()
