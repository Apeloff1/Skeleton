"""Multi-facet/encoded-link trap veto, canonical replay and metered admission."""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.frontier_antichain import vet_url_antichain
from skeleton.ai.webcrawler.frontier_circuit import evaluate_frontier_candidate
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun

ROOT = "https://example.com/catalog"
NORMAL = "https://example.com/flight/wing"
ROBOTS = b"User-agent: *\nAllow: /\n"


class AntichainContracts(unittest.TestCase):
    def evaluate(self, url, *, seen=(), frontier=(), cap=48):
        return vet_url_antichain(url, seen=seen,
                                 frontier=frontier, max_path_variants=cap)

    def test_normal_url_remains_admitted(self):
        row = self.evaluate(ROOT + "?page=1")
        self.assertTrue(row.allowed)
        self.assertFalse(row.network_executed)
        self.assertFalse(row.content_inspected)
        self.assertFalse(row.policy_granted)
        self.assertEqual(len(row.structural_digest), 64)

    def test_double_encoded_credential_query_keys_denied(self):
        for key in ("%2561pi_key", "%2570assword",
                    "access_%2574oken", "client_%2573ecret",
                    "x%252Damz%252Dsignature"):
            with self.subTest(key=key):
                row = self.evaluate(ROOT + "?" + key + "=hidden")
                self.assertFalse(row.allowed)
                self.assertEqual(row.reason, "untrusted_encoded_url_structure")

    def test_decoded_path_structure_changes_denied(self):
        for candidate in (
            ROOT + "/%252e%252e/secrets",
            ROOT + "/%252fadmin",
            ROOT + "/%255cprivate",
            ROOT + "/%253frole=admin",
            ROOT + "/%2523fragment",
        ):
            with self.subTest(candidate=candidate):
                row = self.evaluate(candidate)
                self.assertFalse(row.allowed)

    def test_bounded_facets_across_query_key_sets(self):
        seen = tuple(ROOT + f"?key{i}=a" for i in range(48))
        row = self.evaluate(ROOT + "?key48=a", seen=seen)
        self.assertFalse(row.allowed)
        self.assertEqual(row.reason, "path_facet_variant_budget_exhausted")
        self.assertEqual(row.known_path_variants, 48)
        allowed = self.evaluate("https://example.com/other?new=1", seen=seen)
        self.assertTrue(allowed.allowed)

    def test_shuffled_previous_urls_same_verdict(self):
        seen = [ROOT+f"?facet{i}=x" for i in range(45)]
        a = self.evaluate(ROOT+"?facet99=x", seen=seen, cap=45)
        b = self.evaluate(ROOT+"?facet99=x", seen=list(reversed(seen)), cap=45)
        self.assertEqual(a, b)

    def test_existing_default_single_family_cap_still_precedes_more_variants(self):
        seen = [ROOT+f"?page={i}" for i in range(24)]
        row = evaluate_frontier_candidate(
            ROOT+"?page=24", seen=seen, frontier=[],
        )
        self.assertFalse(row.allowed)
        self.assertEqual(row.reason, "family_variant_circuit_open")

    def test_opaque_query_token_names_are_not_retained(self):
        url = ROOT+"?access_%2574oken=hidden"
        row = self.evaluate(url)
        self.assertEqual(row.reason, "untrusted_encoded_url_structure")
        self.assertNotIn("hidden", row.structural_digest)

    def test_reject_unbounded_previous_state(self):
        with self.assertRaises(ValueError):
            self.evaluate(ROOT, seen=(ROOT,)*1025)
        with self.assertRaises(ValueError):
            self.evaluate(ROOT, cap=49)

    def test_invalid_historical_state_fail_closed(self):
        with self.assertRaises(ValueError):
            self.evaluate(ROOT, seen=("file:///etc/passwd",))

    def test_circuit_runs_antichain_before_enqueue(self):
        row = evaluate_frontier_candidate(
            ROOT+"?%2561pi_key=secret", seen=[], frontier=[],
        )
        self.assertFalse(row.allowed)
        self.assertEqual(row.reason, "untrusted_encoded_url_structure")


class TrapFetcher:
    timeout_seconds = 4
    transport_mode = "scripted_faceted_antichain"
    def __init__(self):
        self.calls = []
    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        if url == "https://example.com/robots.txt":
            return FetchResponse(url, 200, {"content-type": "text/plain"},
                                 ROBOTS, time.time())
        if url != ROOT:
            raise AssertionError("URL trap was dispatched")
        rows = "".join(
            f"<a href='/catalog?facet{i}=x'>Facet{i}</a>"
            for i in range(64)
        )
        rows += (
            "<a href='/catalog?%2561pi_key=secret'>Credential</a>"
            "<a href='/catalog/%252e%252e/secrets'>Parent decode</a>"
            "<a href='/flight/wing'>Normal flight source</a>"
        )
        return FetchResponse(
            url, 200, {"content-type": "text/html"},
            ("<html><title>Archive catalogue</title><body>"
             + rows + "</body></html>").encode(), time.time(),
        )


class CanonicalAntichainTests(unittest.TestCase):
    def acquire(self):
        now = time.time()
        transport = TrapFetcher()
        run = CrawlRun.create(
            CrawlRequest(
                seed_urls=(ROOT,), allowed_hosts=("example.com",),
                query="flight archive", max_depth=1,
                max_requests=80, max_documents=4,
                max_response_bytes=65536, max_total_bytes=262144,
            ),
            scope={"tenant_id": "tenant", "owner_id": "owner"},
            consent={
                "consent_id": "faceted-site-consent",
                "capture_acknowledged": True,
                "source_rights_acknowledged": True,
                "expires_at": now + 3600,
            },
            now=now, fetcher=transport,
        )
        for offset in (1, 3):
            with patch("skeleton.ai.webcrawler.operations.time.time",
                       return_value=now+offset):
                run.run_slice(
                    max_steps=1, max_seconds=1,
                    authorize=lambda: None,
                    cancelled=lambda: False,
                    on_checkpoint=lambda snap, event: None,
                )
        return run, transport

    def test_actual_crawler_limits_heterogeneous_facet_expansion(self):
        run, fetcher = self.acquire()
        snap = run.snapshot()
        links = {item["url"] for item in snap["frontier"]}
        facets = {x for x in links if x.startswith(ROOT+"?facet")}
        self.assertEqual(len(facets), 48)
        self.assertIn(NORMAL, links)
        self.assertNotIn(ROOT+"?%2561pi_key=secret", links)
        self.assertFalse(any("%252e%252e" in x for x in links))
        self.assertEqual(snap["usage"]["requests"], 2)
        self.assertEqual(snap["usage"]["documents"], 1)
        self.assertEqual(len(fetcher.calls), 2)
        self.assertEqual(
            CrawlRun.from_snapshot(snap, fetcher=fetcher).snapshot(), snap,
        )

    def test_circuit_does_not_create_cross_host_grant(self):
        run, fetcher = self.acquire()
        self.assertFalse(any("outside.example.net" in row["url"]
                             for row in run.snapshot()["frontier"]))
        self.assertEqual(len(fetcher.calls), 2)


if __name__ == "__main__":
    unittest.main()
