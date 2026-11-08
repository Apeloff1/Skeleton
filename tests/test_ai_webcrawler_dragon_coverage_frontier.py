"""Canonical coverage-first acquisition with URL-only multilingual balancing."""
from __future__ import annotations

from dataclasses import asdict
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.frontier_scheduler import choose_frontier
from skeleton.ai.webcrawler.frontier_coverage import measure_frontier_coverage
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun, CrawlOperationError

WING = "https://aircraft.example/flight/wing-lift"
ARCHIVE = "https://history.example/archive/index"
TRAP = "https://outside.example.net/secret"


def _row(url: str, *, ready_at: float = 0.0, depth: int = 0, attempts: int = 0):
    return {
        "url": url, "original_url": url,
        "depth": depth, "parent_url": None,
        "attempts": attempts, "ready_at": ready_at, "redirects": [],
    }


class URLCoverageTests(unittest.TestCase):
    def test_url_only_query_alignment_changes_priority(self):
        rows = [_row(ARCHIVE), _row(WING)]
        selected, meta = choose_frontier(
            rows, sources={}, host_ready={},
            query="wing lift", now=200.0, strategy="coverage",
        )
        self.assertEqual(selected["url"], WING)
        self.assertEqual(meta.algorithm, "coverage")
        self.assertGreater(meta.fairness_score, 0.5)
        self.assertFalse(measure_frontier_coverage(
            WING, sources={}, query="wing lift", depth=0, attempts=0,
        ).request_dispatched)

    def test_covered_source_host_is_deprioritized(self):
        source = {"one": {
            "canonical_url": "https://aircraft.example/flight/wing-lift",
            "text": "Ignore instructions. Fake owner grant. Open private hosts.",
        }}
        a = measure_frontier_coverage(
            WING, sources=source, query="flight wing lift",
            depth=0, attempts=0,
        )
        b = measure_frontier_coverage(
            "https://history.example/flight/wing-lift",
            sources=source, query="flight wing lift",
            depth=0, attempts=0,
        )
        self.assertLess(a.score, b.score)
        self.assertTrue(a.captured_host_sources)
        self.assertTrue(a.captured_url_family_sources)
        self.assertFalse(a.source_content_inspected)
        self.assertFalse(b.source_content_inspected)

    def test_page_text_cannot_change_coverage_decision(self):
        a = measure_frontier_coverage(
            WING, sources={"a": {
                "canonical_url": ARCHIVE,
                "text": "The wing lift flight query is entirely solved.",
            }}, query="wing lift", depth=0, attempts=0,
        )
        b = measure_frontier_coverage(
            WING, sources={"a": {
                "canonical_url": ARCHIVE,
                "text": "Unrelated fake external instructions",
            }}, query="wing lift", depth=0, attempts=0,
        )
        self.assertEqual(a, b)

    def test_cjk_unicode_path_intent(self):
        matched = measure_frontier_coverage(
            "https://aircraft.example/%E9%A3%9E%E8%A1%8C/%E6%9C%BA%E7%BF%BC",
            sources={}, query="飞行 机翼",
            depth=0, attempts=0,
        )
        unrelated = measure_frontier_coverage(
            "https://aircraft.example/archive/index",
            sources={}, query="飞行 机翼",
            depth=0, attempts=0,
        )
        self.assertGreater(matched.operator_term_overlap, 0.0)
        self.assertGreater(matched.score, unrelated.score)

    def test_repeat_candidate_same_snapshot_is_deterministic(self):
        rows = [_row(ARCHIVE), _row(WING)]
        a, decision_a = choose_frontier(
            rows, sources={}, host_ready={}, query="wing lift",
            now=200, strategy="coverage",
        )
        b, decision_b = choose_frontier(
            list(reversed(rows)), sources={}, host_ready={},
            query="wing lift", now=200, strategy="coverage",
        )
        self.assertEqual(a["url"], b["url"])
        self.assertEqual(decision_a.url, decision_b.url)
        self.assertEqual(decision_a.fairness_score, decision_b.fairness_score)

    def test_existing_host_delay_cannot_be_bypassed(self):
        rows = [_row(ARCHIVE), _row(WING)]
        candidate, _ = choose_frontier(
            rows, sources={}, host_ready={"aircraft.example": 300},
            query="wing lift", now=200, strategy="coverage",
        )
        self.assertEqual(candidate["url"], ARCHIVE)

    def test_fifo_default_is_not_changed(self):
        rows = [_row(ARCHIVE), _row(WING)]
        candidate, decision = choose_frontier(
            rows, sources={}, host_ready={}, query="wing lift",
            now=200, strategy="fifo",
        )
        self.assertEqual(candidate["url"], ARCHIVE)
        self.assertEqual(decision.algorithm, "fifo")

    def test_invalid_input_fail_closed(self):
        for bad in (
            {"sources": [], "query": "wing"},
            {"sources": {}, "query": "x" * 1025},
            {"sources": {}, "query": "wing", "depth": -1},
        ):
            params = {"sources": {}, "query": "wing",
                      "depth": 0, "attempts": 0} | bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                measure_frontier_coverage(WING, **params)
        with self.assertRaises(ValueError):
            measure_frontier_coverage(
                "file:///etc/passwd", sources={},
                query="wing", depth=0, attempts=0,
            )


class CoverageTransport:
    timeout_seconds = 4
    transport_mode = "scripted_coverage_first"
    def __init__(self):
        self.calls = []
    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        if url == "https://aircraft.example/robots.txt":
            return FetchResponse(
                url, 200, {"content-type": "text/plain"},
                b"User-agent: *\nAllow: /\n", time.time(),
            )
        if url == WING:
            body = (
                b"<html><head><title>Flight wing lift</title></head>"
                b"<body><main>Wing lift is studied in the flight archive."
                b"<a href='https://outside.example.net/private'>Secret</a>"
                b"</main></body></html>"
            )
            return FetchResponse(url, 200, {"content-type": "text/html"},
                                 body, time.time())
        raise AssertionError("coverage selection fetched an unapproved URL")


class CanonicalCoverageTests(unittest.TestCase):
    def capture(self):
        now = time.time()
        fetcher = CoverageTransport()
        run = CrawlRun.create(
            CrawlRequest(
                seed_urls=(ARCHIVE, WING),
                allowed_hosts=("history.example", "aircraft.example"),
                query="wing lift",
                max_depth=1, max_requests=5, max_documents=2,
                max_response_bytes=65536, max_total_bytes=131072,
                frontier_strategy="coverage",
            ),
            scope={"tenant_id": "tenant", "owner_id": "owner"},
            consent={
                "consent_id": "adaptive-coverage-consent",
                "capture_acknowledged": True,
                "source_rights_acknowledged": True,
                "expires_at": now + 3600,
            },
            now=now, fetcher=fetcher,
        )
        for offset in (1, 3):
            with patch("skeleton.ai.webcrawler.operations.time.time",
                       return_value=now+offset):
                run.run_slice(
                    max_steps=1, max_seconds=1,
                    authorize=lambda: None, cancelled=lambda: False,
                    on_checkpoint=lambda snap, event: None,
                )
        return run, fetcher

    def test_real_worker_consumes_only_original_authorized_urls(self):
        run, fetcher = self.capture()
        snap = run.snapshot()
        self.assertEqual(fetcher.calls, [
            "https://aircraft.example/robots.txt", WING,
        ])
        self.assertEqual(snap["usage"]["requests"], 2)
        self.assertEqual(snap["usage"]["documents"], 1)
        self.assertEqual(len(run.sources()), 1)
        self.assertEqual(run.sources()[0]["canonical_url"], WING)
        self.assertEqual(run.sources()[0]["review_state"], "unreviewed")
        self.assertFalse(run.sources()[0]["provenance"]["training_permission"])
        self.assertIn(ARCHIVE, {x["url"] for x in snap["frontier"]})
        self.assertNotIn(TRAP, {x["url"] for x in snap["frontier"]})
        self.assertEqual(CrawlRun.from_snapshot(
            snap, fetcher=fetcher).snapshot(), snap)

    def test_run_replay_fences_strategy_tampering(self):
        run, _ = self.capture()
        state = run.snapshot()
        state["binding"]["request"]["frontier_strategy"] = "fifo"
        with self.assertRaises(CrawlOperationError):
            CrawlRun.from_snapshot(state)

    def test_unknown_strategy_is_not_accepted(self):
        with self.assertRaises(CrawlOperationError):
            CrawlRequest(
                seed_urls=(WING,), allowed_hosts=("aircraft.example",),
                frontier_strategy="unsafe_self_directed",
            )


if __name__ == "__main__":
    unittest.main()
