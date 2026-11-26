"""Real origin-level 429/503 backpressure through finite canonical CrawlRun."""
from __future__ import annotations

import time
import unittest
from unittest.mock import Mock, patch

from skeleton.ai.webcrawler.bound_http import SocketBoundFetcher
from skeleton.ai.webcrawler.dns_binding import ResolvedTarget
from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.host_backpressure import consent_bounded_retry_after, origin_throttle
from skeleton.ai.webcrawler.operations import CrawlOperationError, CrawlRequest, CrawlRun

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


    def test_long_retry_after_survives_checkpoint_and_prevents_early_reopen(self):
        for value, expected in (("900", 902), ("86400000", 3600)):
            with self.subTest(value=value):
                fetcher = ThrottleFetcher(after=value)
                run, at = self.create(fetcher)
                self.tick(run, at + 1)
                self.tick(run, at + 2)
                snap = run.snapshot()
                self.assertAlmostEqual(snap["host_ready"]["example.com"], at + expected)
                resumed = CrawlRun.from_snapshot(snap, fetcher=fetcher)
                self.tick(resumed, at + 303)
                self.assertEqual(len(fetcher.calls), 2)

    def test_retry_authority_horizon(self):
        for headers, expected in (
            ({"Retry-After": "900"}, 900),
            ({"Retry-After": "9999999999999999"}, 1000),
            ({"Retry-After": "Sun, 06 Nov 2090 00:00:00 GMT"}, 1000),
            ({"Retry-After": "10", "retry-after": "2"}, 1000),
            ({"Retry-After": "NaN"}, None),
            ({}, None),
        ):
            with self.subTest(headers=headers):
                self.assertEqual(
                    consent_bounded_retry_after(headers, now=100, expires_at=1100),
                    expected,
                )

    def test_html_robots_error_page_denies_all_capture(self):
        class HtmlRobots(ThrottleFetcher):
            def fetch_once(self, url, *, user_agent, max_bytes):
                self.calls.append(url)
                return FetchResponse(
                    url, 200, {"content-type": "text/html"},
                    b"<html><body>Unexpected upstream page</body></html>", time.time(),
                )
        fetcher = HtmlRobots()
        run, at = self.create(fetcher)
        self.tick(run, at + 1)
        self.tick(run, at + 2)
        self.tick(run, at + 3)
        self.assertEqual(fetcher.calls, ["https://example.com/robots.txt"])
        self.assertEqual(run.status()["source_count"], 0)
        self.assertEqual(run.status()["state"], "completed")

    def test_denied_body_never_reaches_parser(self):
        fetcher = ThrottleFetcher(failure=403)
        run, at = self.create(fetcher)
        self.tick(run, at + 1)
        with patch("skeleton.ai.webcrawler.operations.inspect_download_media",
                   side_effect=AssertionError("denial must never be parsed")):
            result = self.tick(run, at + 2)
        self.assertEqual(result["slice_events"][0]["reason"], "http_403_or_unsupported_type")
        self.assertEqual(run.status()["source_count"], 0)

    def test_cross_host_robots_deferral_is_committed(self):
        class RedirectRobots(ThrottleFetcher):
            def fetch_once(self, url, *, user_agent, max_bytes):
                if url == "https://example.com/robots.txt":
                    self.calls.append(url)
                    return FetchResponse(url, 302, {
                        "location": "https://example.org/robots.txt"
                    }, b"", time.time())
                return super().fetch_once(url, user_agent=user_agent, max_bytes=max_bytes)

        fetcher = RedirectRobots()
        run, at = self.create(fetcher, hosts=("example.com", "example.org"))
        self.tick(run, at + 1)
        # Construct an already-authorized sibling-host cooldown in the
        # fixture; the durable representation itself is validated on restore.
        run._state["host_ready"]["example.org"] = at + 60
        result = self.tick(run, at + 2)
        self.assertEqual(result["slice_events"][0]["reason"], "target_host_cooldown")
        snap = run.snapshot()
        first = next(row for row in snap["frontier"] if row["url"].endswith("/first"))
        self.assertEqual(first["ready_at"], at + 60)
        resumed = CrawlRun.from_snapshot(snap, fetcher=fetcher)
        self.tick(resumed, at + 3)
        self.assertEqual(fetcher.calls, ["https://example.com/robots.txt"])

    def test_interrupted_dispatch_restores_reservation_exactly_once(self):
        fetcher = ThrottleFetcher()
        run, at = self.create(fetcher)
        checkpoints = []

        def checkpoint(snapshot, event):
            if event["kind"] == "dispatch_reserved":
                checkpoints.append(snapshot)
                return
            raise RuntimeError("simulated outcome write failure")

        with patch("skeleton.ai.webcrawler.operations.time.time", return_value=at + 1):
            with self.assertRaises(CrawlOperationError):
                run.run_slice(max_steps=1, max_seconds=1, on_checkpoint=checkpoint)
        self.assertEqual(len(checkpoints), 1)
        reserved = checkpoints[0]
        self.assertEqual(run.snapshot(), reserved)
        self.assertIsNotNone(reserved["pending_dispatch"])
        resumed = CrawlRun.from_snapshot(reserved, fetcher=fetcher)
        result = self.tick(resumed, at + 2)
        self.assertEqual(result["slice_events"][0]["kind"], "interrupted_dispatch")
        self.assertEqual(len(fetcher.calls), 1)
        self.assertIsNone(resumed.snapshot()["pending_dispatch"])
        self.assertEqual(resumed.snapshot()["usage"]["reserved_bytes"],
                         reserved["usage"]["reserved_bytes"])
        self.assertEqual(resumed.snapshot()["usage"]["requests"], 1)
        self.assertEqual(resumed.snapshot()["usage"]["failures"], 1)



class TransportIsolationTests(unittest.TestCase):
    def test_denial_and_overload_bodies_are_not_read(self):
        for status in (403, 429, 503):
            with self.subTest(status=status):
                url = "https://example.com/first"
                target = ResolvedTarget(url, "example.com", 443, ("93.184.216.34",))
                connection, response = Mock(), Mock()
                response.status = status
                response.getheaders.return_value = [
                    ("Content-Length", "999999999"),
                    ("Content-Encoding", "gzip"),
                    ("Retry-After", "900"),
                    ("Retry-After", "1"),
                ]
                response.read1.side_effect = AssertionError("error body must remain unread")
                connection.getresponse.return_value = response
                with (
                    patch("skeleton.ai.webcrawler.bound_http.resolve_target", return_value=target),
                    patch("skeleton.ai.webcrawler.bound_http._PinnedHTTPSConnection", return_value=connection),
                    patch("skeleton.ai.webcrawler.bound_http.threading.Timer"),
                ):
                    result = SocketBoundFetcher().fetch_once(
                        url, user_agent="SkeletonAI-Crawler/1.0", max_bytes=4096,
                    )
                self.assertEqual(result.status, status)
                self.assertEqual(result.body, b"")
                self.assertEqual(result.headers["retry-after"], "86400")
                response.read1.assert_not_called()
                connection.close.assert_called_once()
                headers = connection.request.call_args.kwargs["headers"]
                self.assertEqual(headers["User-Agent"], "SkeletonAI-Crawler/1.0")
                self.assertNotIn("Cookie", headers)
                self.assertNotIn("Authorization", headers)


if __name__ == "__main__":
    unittest.main()
