"""Real origin-level 429/503 backpressure through finite canonical CrawlRun."""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.host_backpressure import origin_throttle
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun

ROBOTS = b"User-agent: *\nAllow: /\n"
PAGE = b"<html><title>Flight</title><body>Verified later: archived flight physics.</body></html>"


class HostThrottleCalculusTests(unittest.TestCase):
    def test_429_retry_after_seconds_applies_to_all_siblings(self):
        row = origin_throttle(429, {"retry-after": "120"}, now=1000, attempts=0)
        self.assertTrue(row.applies)
        self.assertTrue(row.header_accepted)
        self.assertTrue(row.affects_siblings)
        self.assertEqual(row.origin_ready_at, 1120)

    def test_503_date_and_cap(self):
        row = origin_throttle(503, {"retry-after": "Sun, 06 Nov 2090 00:00:00 GMT"}, now=1000, attempts=1)
        self.assertEqual(row.retry_seconds, 300)

    def test_fallback_exponential_and_immutable_not_a_grant(self):
        for attempts, expected in ((0, 2), (1, 4), (2, 8), (3, 16)):
            with self.subTest(attempts=attempts):
                row = origin_throttle(429, {}, now=1000, attempts=attempts)
                self.assertEqual(row.retry_seconds, expected)
                self.assertFalse(row.header_accepted)

    def test_invalid_negative_float_ambiguous_header_does_not_reduce_backoff(self):
        for value in ("-5", "0.1", "NaN", "2, 200", "not-a-date"):
            with self.subTest(value=value):
                row = origin_throttle(429, {"retry-after": value}, now=10, attempts=0)
                self.assertEqual(row.retry_seconds, 2)
                self.assertFalse(row.header_accepted)

    def test_non_throttle_status_never_delays_other_hosts(self):
        for status in (200, 400, 404, 408, 425, 500, 502, 504):
            row = origin_throttle(status, {"retry-after": "300"}, now=1, attempts=2)
            self.assertFalse(row.applies)
            self.assertIsNone(row.origin_ready_at)

    def test_invalid_observation_is_denied(self):
        for status, now, attempts in ((429, float("nan"), 0), (429, 1, True), (True, 10, 0)):
            with self.assertRaises(ValueError):
                origin_throttle(status, {}, now=now, attempts=attempts)


class ThrottleFetcher:
    timeout_seconds = 3
    transport_mode = "scripted_per_origin_retry_contract"

    def __init__(self, failure=429, after="120"):
        self.failure = failure
        self.after = after
        self.calls = []
        self.blocked_once = False

    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchResponse(url, 200, {"content-type": "text/plain"}, ROBOTS, time.time())
        if url == "https://example.com/first" and not self.blocked_once:
            self.blocked_once = True
            return FetchResponse(url, self.failure, {"retry-after": self.after}, b"", time.time())
        return FetchResponse(url, 200, {"content-type": "text/html"}, PAGE, time.time())


class CanonicalThrottleTests(unittest.TestCase):
    def create(self, fetcher, *, hosts=("example.com",)):
        at = time.time()
        request = CrawlRequest(
            seed_urls=(
                "https://example.com/first",
                "https://example.com/second",
            ) + (("https://example.org/third",) if "example.org" in hosts else ()),
            allowed_hosts=hosts, max_requests=12, max_documents=6,
            max_depth=0, min_host_delay_seconds=.25,
            max_response_bytes=4096, max_total_bytes=49152,
        )
        run = CrawlRun.create(request, scope={
            "tenant_id": "tenant", "owner_id": "owner",
        }, consent={
            "consent_id": "retry-consent",
            "capture_acknowledged": True,
            "source_rights_acknowledged": True,
            "expires_at": at + 3600,
        }, now=at, fetcher=fetcher)
        return run, at

    def tick(self, run, at):
        with patch("skeleton.ai.webcrawler.operations.time.time", return_value=at):
            return run.run_slice(
                max_steps=1, max_seconds=1, authorize=lambda: None,
                cancelled=lambda: False, on_checkpoint=lambda snapshot, event: None,
            )

    def test_retry_after_429_cools_siblings_without_stalling_other_host(self):
        fetcher = ThrottleFetcher()
        run, at = self.create(fetcher, hosts=("example.com", "example.org"))
        self.tick(run, at + 1)  # robots example.com
        self.tick(run, at + 2)  # first URL is 429
        snap = run.snapshot()
        self.assertGreaterEqual(snap["host_ready"]["example.com"], at + 122)
        self.tick(run, at + 3)  # other host robots, not same-host sibling
        self.assertEqual(fetcher.calls[:3], [
            "https://example.com/robots.txt",
            "https://example.com/first",
            "https://example.org/robots.txt",
        ])
        self.assertNotIn("https://example.com/second", fetcher.calls)
        self.assertEqual(CrawlRun.from_snapshot(snap, fetcher=fetcher).snapshot(), snap)

    def test_throttle_expiry_reopens_origin(self):
        fetcher = ThrottleFetcher(after="2")
        run, at = self.create(fetcher)
        self.tick(run, at + 1)
        self.tick(run, at + 2)
        self.assertEqual(len(fetcher.calls), 2)
        self.tick(run, at + 2.5)
        self.assertEqual(len(fetcher.calls), 2)
        self.tick(run, at + 5)
        self.tick(run, at + 7)
        self.assertIn("https://example.com/second", fetcher.calls)

    def test_503_conservative_fallback_without_retry_after(self):
        fetcher = ThrottleFetcher(failure=503, after="invalid")
        run, at = self.create(fetcher)
        self.tick(run, at + 1)
        self.tick(run, at + 2)
        self.assertGreaterEqual(run.snapshot()["host_ready"]["example.com"], at + 4)


if __name__ == "__main__":
    unittest.main()
