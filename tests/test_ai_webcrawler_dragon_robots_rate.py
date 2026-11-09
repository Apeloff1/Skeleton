"""Robots Request-rate actually delays real canonical CrawlRun sibling URLs."""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun
from skeleton.ai.webcrawler.robots_rate import (
    RobotsRateError, combine_robots_pacing,
)

PAGE=b"<html><body>Archived flight mechanics and interactive worlds.</body></html>"


class PacingMathTests(unittest.TestCase):
    def test_request_rate_is_actual_minimum_delay(self):
        row=combine_robots_pacing(operator_delay=.25,crawl_delay=None,
                                  requests=2,seconds=10)
        self.assertEqual(row.minimum_seconds,5)
        self.assertFalse(row.denied)

    def test_crawl_delay_and_operator_are_conservative(self):
        self.assertEqual(combine_robots_pacing(
            operator_delay=3,crawl_delay=10,requests=2,seconds=6
        ).minimum_seconds,10)

    def test_oversized_delay_denies_not_truncates(self):
        self.assertTrue(combine_robots_pacing(
            operator_delay=.25,crawl_delay=90000,
        ).denied)

    def test_incomplete_rate_rejected(self):
        with self.assertRaises(RobotsRateError):
            combine_robots_pacing(operator_delay=1,crawl_delay=0,requests=2)


class RobotsRateFetcher:
    timeout_seconds=3
    transport_mode="scripted_robots_rate_canonical_worker"
    def __init__(self):
        self.calls=[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            body=b"User-agent: *\nAllow: /\nRequest-rate: 1/10\n"
            return FetchResponse(url,200,{"content-type":"text/plain"},body,time.time())
        return FetchResponse(url,200,{"content-type":"text/html"},PAGE,time.time())


class RobotsRateLiveTests(unittest.TestCase):
    def create(self):
        at=time.time()
        transport=RobotsRateFetcher()
        run=CrawlRun.create(CrawlRequest(
            seed_urls=("https://example.com/a","https://example.com/b"),
            allowed_hosts=("example.com",),max_depth=0,
            max_requests=5,max_documents=3,max_response_bytes=4096,
            max_total_bytes=16384,min_host_delay_seconds=.25,
        ),scope={"tenant_id":"t","owner_id":"o"},consent={
            "consent_id":"rate-optin","capture_acknowledged":True,
            "source_rights_acknowledged":True,"expires_at":at+3600,
        },now=at,fetcher=transport)
        return run,transport,at

    def tick(self,run,at):
        with patch("skeleton.ai.webcrawler.operations.time.time",return_value=at):
            run.run_slice(max_steps=1,max_seconds=1,authorize=lambda:None,
                cancelled=lambda:False,on_checkpoint=lambda snap,event:None)

    def test_rate_rule_applies_to_successive_pages(self):
        run,fetcher,at=self.create()
        self.tick(run,at+1)
        self.tick(run,at+3)
        self.assertEqual(fetcher.calls,[
            "https://example.com/robots.txt","https://example.com/a",
        ])
        self.assertGreaterEqual(run.snapshot()["host_ready"]["example.com"],at+13)
        self.tick(run,at+7)
        self.assertEqual(len(fetcher.calls),2)
        self.tick(run,at+14)
        self.assertIn("https://example.com/b",fetcher.calls)
        self.assertEqual(CrawlRun.from_snapshot(run.snapshot(),fetcher=fetcher).snapshot(),run.snapshot())


if __name__=="__main__":
    unittest.main()
