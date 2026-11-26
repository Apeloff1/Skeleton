"""Deterministic integration regressions for checkpointed discovery and discourse."""
from __future__ import annotations

import copy
import json
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.dragon_companion import CompanionProfile
from skeleton.ai.webcrawler.frontier_scheduler import choose_frontier
from skeleton.ai.webcrawler.navigation_backlog import (
    MAX_BYTES, deliberate, new_backlog, observe, pending_rows, validate,
)
from skeleton.ai.webcrawler.operations import CrawlRun, CrawlRequest, CrawlOperationError, _digest


class OfflineFetcher:
    timeout_seconds = 3
    transport_mode = "scripted_navigation_fixture"

    def __init__(self):
        self.calls = []

    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            body = b"User-agent: *\nAllow: /\nSitemap: https://example.com/sitemap.txt\n"
            return FetchResponse(url, 200, {"content-type": "text/plain"}, body, time.time())
        if url.endswith("/sitemap.txt"):
            body = b"https://example.com/flight\nhttps://example.com/landing\n"
            return FetchResponse(url, 200, {"content-type": "text/plain"}, body, time.time())
        body = b'<html><title>Navigation</title><body><p>Flight mechanics reference.</p><a href="/guide">Guide</a><a href="/flight">Flight</a><a href="https://example.org/private">Outside</a></body></html>'
        return FetchResponse(url, 200, {"content-type": "text/html"}, body, time.time())


def create(*, depth=2, strategy="companion", fetcher=None):
    now = time.time()
    req = CrawlRequest(seed_urls=("https://example.com/start",),
        allowed_hosts=("example.com",), query="flight mechanics",
        max_depth=depth, max_requests=24, max_documents=16,
        min_host_delay_seconds=.25, discover_sitemaps=True, frontier_strategy=strategy)
    return CrawlRun.create(req, scope={"tenant_id": "tenant", "owner_id": "owner"},
        consent={"consent_id": "explicit-grant", "capture_acknowledged": True,
            "source_rights_acknowledged": True, "expires_at": now + 3600},
        now=now, fetcher=fetcher or OfflineFetcher()), now


def tick(run, at):
    with patch("skeleton.ai.webcrawler.operations.time.time", return_value=at):
        return run.run_slice(max_steps=1, max_seconds=2, authorize=lambda: None,
                             cancelled=lambda: False, on_checkpoint=lambda snap, event: None)


class NavigationBacklogTests(unittest.TestCase):
    def test_overflow_is_durable_then_promoted_without_dispatch(self):
        run, now = create(strategy="fifo")
        with patch("skeleton.ai.webcrawler.operations.MAX_FRONTIER", 2):
            for path in ("guide", "flight", "landing"):
                self.assertTrue(run._enqueue("https://example.com/" + path,
                                 depth=1, parent_url="https://example.com/start"))
            snapshot = run.snapshot()
            self.assertEqual(len(snapshot["frontier"]), 2)
            self.assertEqual(len(pending_rows(snapshot["discovery_backlog"])), 2)
            replay = CrawlRun.from_snapshot(json.loads(json.dumps(snapshot, sort_keys=True)))
            self.assertEqual(replay.snapshot(), snapshot)
            replay._finish_item(replay._state["frontier"][0])
            replay._replenish_frontier(now)
            self.assertEqual(replay._state["frontier"][-1]["url"], "https://example.com/flight")
            self.assertEqual(replay._state["usage"]["requests"], 0)
            self.assertEqual(replay.status()["navigation_backlog"]["counts"]["promoted"], 1)

    def test_depth_holds_and_outside_scope_never_become_pending(self):
        run, _ = create(depth=0)
        self.assertFalse(run._enqueue("https://example.com/guide", depth=1,
                                     parent_url="https://example.com/start"))
        self.assertFalse(run._enqueue("https://example.org/private", depth=0, parent_url=None))
        self.assertFalse(run._enqueue("https://example.com/?token=secret", depth=0, parent_url=None))
        ledger = run.snapshot()["discovery_backlog"]
        self.assertEqual(ledger["counts"]["depth_held"], 1)
        self.assertEqual(ledger["counts"]["outside_policy"], 2)
        self.assertFalse(pending_rows(ledger))
        self.assertNotIn("secret", json.dumps(ledger))
        self.assertNotIn("example.org", json.dumps(ledger))

    def test_duplicate_metadata_retains_bounded_provenance(self):
        run, _ = create()
        for parent in ("start", "archive", "sitemap.txt"):
            run._enqueue("https://example.com/guide#heading", depth=1,
                         parent_url="https://example.com/" + parent,
                         relation="sitemap_urlset" if parent == "sitemap.txt" else "document_link")
        ledger = run.snapshot()["discovery_backlog"]
        record = next(row for row in ledger["records"].values()
                      if row["url"] == "https://example.com/guide")
        self.assertEqual(record["observations"], 3)
        self.assertEqual(len(record["parents"]), 3)
        self.assertEqual(record["relations"], ["document_link", "sitemap_urlset"])

    def test_recomputed_digest_does_not_accept_out_of_scope_backlog(self):
        run, _ = create()
        snapshot = run.snapshot()
        bad = copy.deepcopy(snapshot)
        row = next(iter(bad["discovery_backlog"]["records"].values()))
        row["parents"] = ["https://example.org/forbidden"]
        bad.pop("snapshot_digest")
        bad["snapshot_digest"] = _digest(bad)
        with self.assertRaises(CrawlOperationError):
            CrawlRun.from_snapshot(bad)

    def test_parser_discovery_and_document_share_checkpoint(self):
        fetcher = OfflineFetcher()
        run, now = create(strategy="fifo", fetcher=fetcher)
        for i in range(1, 6):
            tick(run, now + i)
        ledger = run.snapshot()["discovery_backlog"]
        relations = {kind for row in ledger["records"].values() for kind in row["relations"]}
        self.assertIn("robots_sitemap", relations)
        self.assertIn("document_link", relations)
        self.assertTrue({"structured", "sitemap_urlset"} & relations)
        self.assertNotIn("https://example.org/private", json.dumps(ledger))
        self.assertTrue(all("example.com" in url for url in fetcher.calls))

    def test_capacity_is_explicit_not_silent(self):
        ledger = new_backlog()
        with patch("skeleton.ai.webcrawler.navigation_backlog.MAX_RECORDS", 2):
            for i in range(4):
                observe(ledger, url=f"https://example.com/guide/{i}",
                        parent=None, depth=0, kind="seed")
            self.assertEqual(len(ledger["records"]), 2)
            self.assertEqual(ledger["counts"]["capacity_omissions"], 2)
            validate(ledger, admit=lambda url: url, max_depth=0)
        self.assertLess(len(json.dumps(ledger)), MAX_BYTES)


class JointDiscourseTests(unittest.TestCase):
    def profile(self, quest="synthesize"):
        return CompanionProfile({"energy": .9, "style": "scholarly"},
            {"example.com": .3}, {"example.com": .45}, {"example.com": 3},
            {"flight": 0, "mechanics": 6}, frozenset({"example.com"}), quest)

    def row(self, name, ready=0):
        return {"url": "https://example.com/" + name, "depth": 1,
                "attempts": 0, "ready_at": ready}

    def test_gap_and_independent_counterproposal_visible(self):
        p = self.profile()
        a = deliberate(self.row("flight"), base=.5, query="flight mechanics", profile=p)
        b = deliberate(self.row("mechanics"), base=.5, query="flight mechanics", profile=p)
        self.assertGreater(a.uncovered_terms, b.uncovered_terms)
        self.assertGreater(a.jeeves_proposal, b.jeeves_proposal)
        self.assertNotEqual(a.jeeves_proposal, a.dragon_counterproposal)
        self.assertEqual(a.receipt(), deliberate(self.row("flight"), base=.5,
                         query="flight mechanics", profile=p).receipt())

    def test_recovery_preserves_measured_base(self):
        d = deliberate(self.row("flight"), base=.42, query="flight",
                       profile=self.profile("recover"))
        self.assertEqual(d.final_priority, .42)

    def test_scheduler_never_selects_cooling_item_or_grants_transport(self):
        chosen, decision = choose_frontier([self.row("flight", 100), self.row("guide")],
            sources={}, host_ready={}, query="flight", now=10,
            strategy="companion", companion=self.profile())
        self.assertEqual(chosen["url"], "https://example.com/guide")
        self.assertFalse(decision.actual_dispatch_authorized)
        self.assertEqual(decision.discourse["authority"], "advisory_only")

    def test_canonical_dispatch_records_discourse(self):
        run, now = create()
        tick(run, now + 1)
        receipt = run.status()["navigation_backlog"]["last_discourse"]
        self.assertEqual(receipt["authority"], "advisory_only")
        self.assertEqual(CrawlRun.from_snapshot(run.snapshot()).status()
                         ["navigation_backlog"]["last_discourse"], receipt)


if __name__ == "__main__":
    unittest.main()
