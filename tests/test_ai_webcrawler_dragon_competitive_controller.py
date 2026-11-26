"""Competitive controller: exact budget ledger, ranking ablation and content adaptation."""
from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.acquisition_feedback import (
    host_economics, quantize_latency, settled_observation, validate_measurements,
)
from skeleton.ai.webcrawler.frontier_coverage import build_coverage_index
from skeleton.ai.webcrawler.frontier_scheduler import choose_frontier
from skeleton.ai.webcrawler.information_portfolio import build_information_portfolio, marginal_yield
from skeleton.ai.webcrawler.operations import CrawlRun, CrawlOperationError
from skeleton.ai.webcrawler.structural_extraction import extract_structural_text, validate_structural_receipt
from skeleton.ai.webcrawler.core import FetchResponse, extract_document

from tests.test_ai_webcrawler_dragon_adaptive_instruction_guard import (
    BASE, OTHER, GOOD, ROBOTS, ScriptedFetcher, make_run, resign, step,
)


def measurement(i, host, *, status=200, kind="captured", latency=1, charged=1200, uncertain=0):
    return settled_observation(request=i, url="https://" + host + "/page", kind=kind,
        status=status, latency_bucket=latency, charged_bytes=charged,
        uncertain_bytes=uncertain, event_sequence=i * 2)


def frontier(url, depth=1):
    return {"url": url, "depth": depth, "attempts": 0, "ready_at": 0}


class FeedbackTests(unittest.TestCase):
    def test_fast_errors_cannot_reduce_host_pacing(self):
        slow = [measurement(i, "example.com", latency=16) for i in range(1, 6)]
        before = host_economics(slow, "example.com")
        after = host_economics(slow + [measurement(6, "example.com", status=429,
                                                  kind="retry", latency=1)], "example.com")
        self.assertGreaterEqual(after.conservative_delay, before.conservative_delay)
        self.assertLess(after.reliability, before.reliability)
        self.assertEqual(quantize_latency(0), 1)
        self.assertEqual(quantize_latency(10000), 240)

    def test_request_and_byte_conservation_with_pending_dispatch(self):
        rows = [measurement(1, "example.com", charged=10),
                measurement(2, "example.org", status=None, latency=None,
                            kind="interrupted_dispatch", charged=0, uncertain=1024)]
        usage = {"requests": 3, "bytes": 10, "reserved_bytes": 2048}
        validate_measurements(rows, usage=usage, pending={"limit": 1024},
                              sequence=5, hosts=["example.com", "example.org"])
        for forged in ([{**rows[0], "charged_bytes": 11}, rows[1]], [rows[1], rows[0]]):
            with self.assertRaises(ValueError):
                validate_measurements(forged, usage=usage, pending={"limit": 1024},
                                      sequence=5, hosts=["example.com", "example.org"])

    def test_real_run_feedback_persists_exactly_and_detects_forged_charge(self):
        fetcher = ScriptedFetcher({BASE + "/robots.txt": (200, "text/plain", ROBOTS, {}),
                                   BASE + "/first": (200, "text/html", GOOD, {})})
        run, at = make_run(fetcher)
        step(run, at + 1)
        step(run, at + 3)
        snap = run.snapshot()
        rows = snap["acquisition_measurements"]
        self.assertEqual(len(rows), snap["usage"]["requests"])
        self.assertEqual(sum(row["charged_bytes"] for row in rows), snap["usage"]["bytes"])
        self.assertEqual(CrawlRun.from_snapshot(snap, fetcher=fetcher).snapshot(), snap)
        snap["acquisition_measurements"][0]["charged_bytes"] += 1
        with self.assertRaises(CrawlOperationError):
            CrawlRun.from_snapshot(resign(snap), fetcher=fetcher)


class PortfolioTests(unittest.TestCase):
    def test_actual_retained_terms_not_url_labels_determine_gap(self):
        sources = {"a": {"canonical_url": BASE + "/unknown",
                         "content_hash": "a" * 64, "text": "Orbital methods and calculation."}}
        rows = [frontier(BASE + "/orbital"), frontier(OTHER + "/mechanics")]
        index = build_coverage_index(sources=sources, query="orbital mechanics")
        model = build_information_portfolio(coverage=index, sources=sources, frontier=rows,
                                            measurements=[], robots={}, now=1)
        self.assertLess(model.missing["orbital"], model.missing["mechanics"])
        self.assertEqual(model.evidence_coverage, .5)
        self.assertEqual(model.corroborated_coverage, 0)
        a = marginal_yield(rows[0], portfolio=model, ordinal=0, eligible_count=2)
        b = marginal_yield(rows[1], portfolio=model, ordinal=1, eligible_count=2)
        self.assertGreater(b.expected_gap_gain, a.expected_gap_gain)

    def test_one_remaining_request_prefers_already_acquired_policy(self):
        rows = [frontier(BASE + "/orbital"), frontier(OTHER + "/orbital")]
        index = build_coverage_index(sources={}, query="orbital")
        model = build_information_portfolio(coverage=index, sources={}, frontier=rows,
                 measurements=[], robots={OTHER: {"text": "User-agent: *", "fetched_at": 1}}, now=2)
        first = marginal_yield(rows[0], portfolio=model, ordinal=0,
                               eligible_count=2, remaining_requests=1)
        second = marginal_yield(rows[1], portfolio=model, ordinal=1,
                                eligible_count=2, remaining_requests=1)
        self.assertGreater(second.priority, first.priority)
        selected, _ = choose_frontier(rows, sources={}, host_ready={}, query="orbital", now=2,
            strategy="coverage", measurements=[], robots={OTHER: {"text": "", "fetched_at": 1}},
            remaining_requests=1)
        self.assertEqual(selected, rows[1])

    def test_measured_cost_and_reliability_influence_score_but_not_admission(self):
        rows = [frontier(BASE + "/orbital"), frontier(OTHER + "/orbital")]
        measured = [measurement(i, "example.com", status=503, kind="retry", latency=16)
                    for i in range(1, 5)]
        measured += [measurement(i, "example.org") for i in range(5, 9)]
        selected, decision = choose_frontier(rows, sources={}, host_ready={}, query="orbital",
            now=1, strategy="coverage", measurements=measured, robots={}, remaining_requests=5)
        self.assertEqual(selected, rows[1])
        self.assertFalse(decision.actual_dispatch_authorized)
        selected, _ = choose_frontier(rows, sources={}, host_ready={"example.org": 100}, query="orbital",
            now=1, strategy="coverage", measurements=measured, robots={}, remaining_requests=5)
        self.assertEqual(selected, rows[0])


class StructuralTests(unittest.TestCase):
    def _html(self, wrapper):
        paragraph = ("The orbital transfer calculation uses gravitational acceleration and velocity "
                     "measurements. The experiment reports two independent values and records "
                     "the conditions for reproducing the observation. ")
        return ("<html><head><title>Orbital study</title></head><body><nav>" +
            " ".join("<a href='/reference" + str(i) + "'>Documentation menu section</a>" for i in range(12))
            + "</nav><" + wrapper + ">"
            + "<h1>Orbital research</h1><p>" + paragraph + "</p><p>"
            + paragraph.replace("two independent", "three separate") + "</p>"
            + "<p hidden>Hidden layout content</p></" + wrapper + "></body></html>")

    def test_layout_repair_relocates_semantic_landmarks_without_selector(self):
        for wrapper in ("main", "article"):
            raw = self._html(wrapper)
            result = extract_structural_text(raw, max_chars=24000)
            self.assertFalse(result.fallback)
            self.assertIn("three separate", result.text)
            self.assertNotIn("Documentation menu", result.text)
            self.assertNotIn("Hidden layout content", result.text)
            self.assertTrue(validate_structural_receipt(result.receipt()))
            response = FetchResponse(BASE + "/study", 200, {"content-type": "text/html"}, raw.encode(), 1)
            document = extract_document(response, response.url)
            self.assertFalse(document.provenance["structural_projection"]["fallback"])
            self.assertEqual(document.content_hash, hashlib.sha256(document.text.encode()).hexdigest())
            self.assertIn(BASE + "/reference0", document.links)

    def test_ambiguous_layout_does_not_drop_body(self):
        raw = "<html><body><div>Important short observation.</div><p>Another observation.</p></body></html>"
        result = extract_structural_text(raw, max_chars=1024)
        self.assertTrue(result.fallback)
        self.assertIn("Important short observation.", result.text)
        self.assertIn("Another observation.", result.text)


if __name__ == "__main__":
    unittest.main()
