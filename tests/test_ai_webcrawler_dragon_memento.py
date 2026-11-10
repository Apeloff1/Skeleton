"""Opt-in Memento navigation remains same-origin and consent/robots controlled."""
from __future__ import annotations
from email.utils import formatdate
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import CrawlPolicy, FetchResponse
from skeleton.ai.webcrawler.memento_relations import (
    MementoDiscoveryError, discover_mementos,
)
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun

SOURCE = "https://example.com/research/flight"
POLICY = CrawlPolicy(allowed_hosts=frozenset({"example.com", "archive.example.net"}))
HISTORY = "https://example.com/history/2020/flight"
FOREIGN = "https://archive.example.net/history/flight"


def header(now):
    old = formatdate(now - 86400, usegmt=True)
    future = formatdate(now + 86400, usegmt=True)
    return {"Link": (
        f'<{HISTORY}>; rel="memento"; datetime="{old}", '
        f'<{FOREIGN}>; rel="memento"; datetime="{old}", '
        f'</timemap>; rel="timemap"; type="application/link-format", '
        f'</timegate>; rel="timegate", '
        f'</history/latest>; rel="memento"; datetime="{future}"'
    )}


class MementoParserTests(unittest.TestCase):
    def evaluate(self, headers, now=None, max_links=8):
        stamp = time.time() if now is None else now
        return discover_mementos(
            headers, base_url=SOURCE, policy=POLICY,
            observed_at=stamp, max_links=max_links,
        )

    def test_only_past_same_origin_memento(self):
        stamp = time.time()
        report = self.evaluate(header(stamp), now=stamp)
        self.assertEqual(report.links, (HISTORY,))
        self.assertGreaterEqual(report.checked_relations, 4)
        self.assertGreaterEqual(report.rejected, 2)
        self.assertTrue(report.historical_urls_not_verified)
        self.assertFalse(report.network_requests_started)
        self.assertFalse(report.grants_network_authority)
        self.assertFalse(report.consent_expiry_extended)

    def test_future_history_is_not_authority(self):
        stamp = time.time()
        row = self.evaluate({
            "link": (f'<{HISTORY}>; rel=memento; datetime="'
                     f'{formatdate(stamp + 86400, usegmt=True)}"'),
        }, now=stamp)
        self.assertEqual(row.links, ())

    def test_malformed_date_denied(self):
        row = self.evaluate({
            "Link": f'<{HISTORY}>; rel=memento; datetime="not-a-date"',
        })
        self.assertEqual(row.links, ())
        self.assertEqual(row.rejected, 1)

    def test_cross_origin_and_userinfo_denied(self):
        old = formatdate(time.time() - 10000, usegmt=True)
        row = self.evaluate({
            "Link": (
                f'<https://user:secret@example.com/private>; rel=memento; datetime="{old}", '
                f'<{FOREIGN}>; rel=memento; datetime="{old}"'
            ),
        })
        self.assertEqual(row.links, ())

    def test_duplicate_headers_denied(self):
        with self.assertRaises(MementoDiscoveryError):
            self.evaluate({"link": "one", "Link": "two"})

    def test_unbalanced_header_denied(self):
        with self.assertRaises(MementoDiscoveryError):
            self.evaluate({"link": f'<{HISTORY}; rel=memento'})

    def test_empty_header_no_discovery(self):
        self.assertEqual(self.evaluate({}).links, ())

    def test_oversized_header_denied(self):
        with self.assertRaises(MementoDiscoveryError):
            self.evaluate({"link": "x" * 8193})

    def test_duplicate_historical_urls_deduplicated(self):
        now = time.time()
        then = formatdate(now - 3600, usegmt=True)
        unit = f'<{HISTORY}>; rel=memento; datetime="{then}"'
        row = self.evaluate({"link": unit+", "+unit}, now=now)
        self.assertEqual(row.links, (HISTORY,))
        self.assertEqual(row.rejected, 1)


class MementoFetcher:
    timeout_seconds = 4
    transport_mode = "scripted_memento_canonical"
    def __init__(self):
        self.calls = []
    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        if url == "https://example.com/robots.txt":
            return FetchResponse(url, 200, {"content-type": "text/plain"},
                                 b"User-agent: *\nAllow: /\n", time.time())
        if url == SOURCE:
            return FetchResponse(
                url, 200, {"content-type": "text/html", **header(time.time())},
                b"<html><head><title>Flight records</title></head>"
                b"<body>Original aircraft test records.</body></html>",
                time.time(),
            )
        raise AssertionError("temporal URL dispatched before frontier admission")


class CanonicalMementoTests(unittest.TestCase):
    def capture(self, enabled):
        now = time.time()
        fetcher = MementoFetcher()
        run = CrawlRun.create(
            CrawlRequest(
                seed_urls=(SOURCE,),
                allowed_hosts=("example.com", "archive.example.net"),
                discover_mementos=enabled,
                max_requests=4, max_documents=2, max_depth=1,
                max_response_bytes=65536, max_total_bytes=131072,
            ),
            scope={"tenant_id": "tenant", "owner_id": "owner"},
            consent={"consent_id": "memento-consent",
                     "capture_acknowledged": True,
                     "source_rights_acknowledged": True,
                     "expires_at": now+3600},
            now=now, fetcher=fetcher,
        )
        for delta in (1, 3):
            with patch("skeleton.ai.webcrawler.operations.time.time",
                       return_value=now+delta):
                run.run_slice(max_steps=1, max_seconds=1,
                              authorize=lambda: None, cancelled=lambda: False,
                              on_checkpoint=lambda snap,event: None)
        return run,fetcher

    def test_default_disables_temporal_expansion(self):
        run,fetcher = self.capture(False)
        state = run.snapshot()
        self.assertEqual(state["usage"]["requests"], 2)
        self.assertEqual(state["usage"]["documents"], 1)
        self.assertEqual(state["frontier"], [])
        self.assertEqual(len(fetcher.calls), 2)

    def test_opt_in_puts_memento_on_original_frontier(self):
        run,fetcher = self.capture(True)
        state = run.snapshot()
        self.assertEqual(state["usage"]["requests"], 2)
        self.assertEqual(state["usage"]["documents"], 1)
        self.assertEqual({x["url"] for x in state["frontier"]}, {HISTORY})
        self.assertEqual(len(fetcher.calls), 2)
        self.assertFalse(run.sources()[0]["provenance"]["training_permission"])
        self.assertEqual(CrawlRun.from_snapshot(
            state,fetcher=fetcher).snapshot(),state)

    def test_invalid_opt_in_type_denied(self):
        with self.assertRaises(ValueError):
            CrawlRequest(
                seed_urls=(SOURCE,), allowed_hosts=("example.com",),
                discover_mementos="true",
            )

    def test_snapshot_cannot_change_history_opt_in(self):
        run,_ = self.capture(False)
        state = run.snapshot()
        state["binding"]["request"]["discover_mementos"] = True
        with self.assertRaises(ValueError):
            CrawlRun.from_snapshot(state)


if __name__ == "__main__":
    unittest.main()
