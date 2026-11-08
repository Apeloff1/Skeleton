"""Canonical URL-pattern, credential and calendar-trap frontier admission tests."""
from __future__ import annotations
import time
import unittest
from unittest.mock import patch
from skeleton.ai.webcrawler.frontier_circuit import evaluate_frontier_candidate
from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRun,CrawlRequest

ROOT="https://example.com/browse"
ROBOTS=b"User-agent: *\nAllow: /\n"

def page():
    links="".join(
        f'<a href="/browse?page={i}">Page {i}</a>'
        for i in range(1,41)
    )
    return (
        "<html><head><title>Flight archives</title></head><body>"
        +links
        +'<a href="/browse?access_token=SECRET">Private access link</a>'
        +'<a href="/a/a/a/a/a/a">Repetitive trap</a>'
        +'<a href="/browse?page=99999999">Fake deep index</a>'
        +'<a href="/flight/chapter">Independent document</a>'
        +"</body></html>"
    ).encode()

class CircuitContractTests(unittest.TestCase):
    def decision(self,url,seen=(),frontier=(),max_variants=24):
        return evaluate_frontier_candidate(
            url,seen=seen,frontier=frontier,max_variants=max_variants,
        )
    def test_regular_links_are_advisory_only(self):
        row=self.decision("https://example.com/flight/scene")
        self.assertTrue(row.allowed)
        self.assertEqual(row.reason,"bounded_new_candidate")
        self.assertTrue(row.existing_authority_required)
        self.assertFalse(row.network_executed)
        self.assertEqual(len(row.family_digest),64)
    def test_source_credential_query_rejected(self):
        for token in ("api_key","access_token","authorization",
                      "session_id","x-amz-signature","secret"):
            with self.subTest(token=token):
                row=self.decision(f"https://example.com/browse?{token}=value")
                self.assertFalse(row.allowed)
                self.assertEqual(row.reason,"credential_or_unbounded_query_key")
    def test_canonical_pagination_family_capacity(self):
        urls=[f"https://example.com/browse?page={i}" for i in range(1,25)]
        row=self.decision("https://example.com/browse?page=25",frontier=urls)
        self.assertFalse(row.allowed)
        self.assertEqual(row.reason,"family_variant_circuit_open")
        self.assertEqual(row.family_variants,24)
        other=self.decision("https://example.com/catalog?page=1",frontier=urls)
        self.assertTrue(other.allowed)
    def test_date_segment_families_are_bounded(self):
        urls=[f"https://example.com/archive/2026/11/{i:02d}" for i in range(1,25)]
        row=self.decision("https://example.com/archive/2026/11/25",seen=urls)
        self.assertFalse(row.allowed)
        self.assertEqual(row.family_variants,24)
    def test_very_deep_numeric_page_denied(self):
        row=self.decision("https://example.com/browse?page=999999999")
        self.assertFalse(row.allowed)
        self.assertEqual(row.reason,"pagination_numeric_trap")
    def test_repetitive_path_trap(self):
        row=self.decision("https://example.com/a/a/a/a")
        self.assertTrue(row.allowed)
        row=self.decision("https://example.com/article/article/article/article/article")
        self.assertFalse(row.allowed)
        self.assertEqual(row.reason,"repeated_path_segment_trap")
    def test_same_url_does_not_enter_twice(self):
        url="https://example.com/browse?page=1"
        row=self.decision(url,seen=(url,))
        self.assertFalse(row.allowed)
        self.assertEqual(row.reason,"exact_url_already_known")
    def test_conservative_count_is_deterministic_across_reordering(self):
        urls=[f"https://example.com/browse?page={i}" for i in range(3,19)]
        first=self.decision(ROOT+"?page=20",seen=urls[:8],frontier=urls[8:])
        again=self.decision(ROOT+"?page=20",
                            seen=tuple(reversed(urls[8:])),
                            frontier=tuple(reversed(urls[:8])))
        self.assertEqual(first,again)
        self.assertEqual(first.family_variants,16)
    def test_invalid_limits_fail_closed(self):
        with self.assertRaises(ValueError):
            self.decision(ROOT,seen=("https://example.com/y",)*513)
        with self.assertRaises(ValueError):
            self.decision(ROOT,max_variants=0)

class ScriptedTrapFetcher:
    timeout_seconds=4
    transport_mode="scripted_frontier_circuit"
    def __init__(self):
        self.calls=[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},ROBOTS,time.time())
        if url!=ROOT:
            raise AssertionError("unadmitted trap or pagination link fetched")
        body=page()
        if len(body)>max_bytes:
            raise AssertionError("scripted source budget exceeded")
        return FetchResponse(url,200,{"content-type":"text/html"},body,time.time())

class CanonicalFrontierCircuitTests(unittest.TestCase):
    def capture(self):
        now=time.time()
        fetcher=ScriptedTrapFetcher()
        run=CrawlRun.create(
            CrawlRequest(seed_urls=(ROOT,),allowed_hosts=("example.com",),
                         max_depth=1,max_requests=64,max_documents=4,
                         max_response_bytes=65536,max_total_bytes=262144),
            scope={"tenant_id":"tenant","owner_id":"owner"},
            consent={"consent_id":"frontier-trap-rights",
                     "capture_acknowledged":True,
                     "source_rights_acknowledged":True,
                     "expires_at":now+3600},
            now=now,fetcher=fetcher)
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",return_value=now+offset):
                run.run_slice(max_steps=1,max_seconds=1,
                              authorize=lambda:None,cancelled=lambda:False,
                              on_checkpoint=lambda snap,event:None)
        return run,fetcher
    def test_actual_crawler_denies_traps_with_no_extra_http(self):
        run,fetcher=self.capture()
        state=run.snapshot()
        urls={row["url"] for row in state["frontier"]}
        pages=sorted(x for x in urls if x.startswith(ROOT+"?page="))
        self.assertEqual(len(pages),24)
        self.assertIn("https://example.com/flight/chapter",urls)
        self.assertNotIn(ROOT+"?access_token=SECRET",urls)
        self.assertNotIn("https://example.com/a/a/a/a/a/a",urls)
        self.assertNotIn(ROOT+"?page=99999999",urls)
        self.assertEqual(state["usage"]["requests"],2)
        self.assertEqual(state["usage"]["documents"],1)
        self.assertEqual(len(fetcher.calls),2)
        self.assertEqual(
            CrawlRun.from_snapshot(state,fetcher=fetcher).snapshot(),state,
        )
    def test_consistent_family_cap_after_snapshot_recovery(self):
        run,fetcher=self.capture()
        rebuilt=CrawlRun.from_snapshot(run.snapshot(),fetcher=fetcher)
        first=rebuilt.snapshot()
        self.assertEqual(len(first["frontier"]),25)
        self.assertEqual(first["usage"]["requests"],2)
        self.assertFalse(any("SECRET" in row["url"] for row in first["frontier"]))

if __name__=="__main__":
    unittest.main()
