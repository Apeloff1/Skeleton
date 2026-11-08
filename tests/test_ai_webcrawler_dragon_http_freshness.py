"""Finite HTTP source metadata, no-store custody, privacy and exact replay."""
from __future__ import annotations

import hashlib
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.http_freshness import (
    observe_http_freshness,verify_freshness_receipt,FreshnessError,
)
from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRun,CrawlRequest

NOW=1794052800.0
HTTP_HEADERS={
    "ETag":'"opaque-SECRET_ETAG"',
    "Last-Modified":"Fri, 06 Nov 2026 09:00:00 GMT",
    "Date":"Sat, 07 Nov 2026 12:00:00 GMT",
    "Cache-Control":"public, max-age=3600, stale-while-revalidate=300",
    "Age":"120",
    "Content-Language":"en,fr",
    "Vary":"Accept-Language, Accept-Encoding",
}

class FreshnessParserTests(unittest.TestCase):
    def test_privacy_preserving_validator_and_due_advice(self):
        row=observe_http_freshness(HTTP_HEADERS,observed_at=NOW)
        self.assertEqual(row.etag_digest,hashlib.sha256(
            b'"opaque-SECRET_ETAG"').hexdigest())
        self.assertEqual(row.advisory_due_unix,NOW+3480)
        self.assertEqual(row.max_age_seconds,3600)
        self.assertEqual(row.stale_while_revalidate_seconds,300)
        self.assertEqual(row.age_seconds,120)
        self.assertEqual(row.languages,("en","fr"))
        self.assertEqual(row.vary_dimensions,("accept-encoding","accept-language"))
        self.assertFalse(row.sensitive_vary)
        self.assertFalse(row.grants_new_consent)
        self.assertFalse(row.network_executed)
        self.assertTrue(row.headers_untrusted)
        self.assertTrue(verify_freshness_receipt(row.__dict__,observed_at=NOW))

    def test_no_store_blocks_cache_due_not_authorizes_recrawl(self):
        row=observe_http_freshness({"Cache-Control":"no-store, max-age=300"},
                                   observed_at=NOW)
        self.assertTrue(row.no_store)
        self.assertIsNone(row.advisory_due_unix)
        self.assertFalse(row.grants_new_consent)

    def test_no_cache_disables_due(self):
        row=observe_http_freshness({"Cache-Control":"no-cache, max-age=300"},
                                   observed_at=NOW)
        self.assertTrue(row.no_cache)
        self.assertIsNone(row.advisory_due_unix)

    def test_sensitive_vary_not_retained_raw(self):
        row=observe_http_freshness(
            {"Vary":"Cookie, Authorization, Accept-Language"},observed_at=NOW)
        self.assertTrue(row.sensitive_vary)
        self.assertEqual(row.vary_dimensions,("accept-language",))

    def test_malicious_headers_rejected(self):
        invalid=[
            {"ETag":"x"*513},
            {"ETag":"one","etag":"two"},
            {"Cache-Control":"max-age=9999999999"},
            {"Cache-Control":"max-age=nan"},
            {"Content-Language":"en,\nsecret"},
            {"Vary":"Cookie,"*30},
            {"Age":"-1"},
            {"Last-Modified":"not a date"},
        ]
        for headers in invalid:
            with self.subTest(headers=headers),self.assertRaises(FreshnessError):
                observe_http_freshness(headers,observed_at=NOW)

    def test_receipt_tamper_guard(self):
        value=observe_http_freshness(HTTP_HEADERS,observed_at=NOW).__dict__.copy()
        for key,bad in (
            ("age_seconds",-1),
            ("no_store","false"),
            ("etag_digest","SECRET_ETAG"),
            ("grants_new_consent",True),
            ("network_executed",True),
            ("advisory_due_unix",NOW+10000000),
        ):
            with self.subTest(key=key):
                changed={**value,key:bad}
                self.assertFalse(verify_freshness_receipt(changed,observed_at=NOW))
        value.pop("schema")
        self.assertFalse(verify_freshness_receipt(value,observed_at=NOW))

class HTTPFetcher:
    timeout_seconds=4
    transport_mode="scripted_http_validator_capture"
    def __init__(self,no_store=False):
        self.no_store=no_store
        self.calls=[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/source":
            raise AssertionError("freshness headers attempted remote request")
        headers={k.lower():v for k,v in HTTP_HEADERS.items()}
        headers["content-type"]="text/html"
        if self.no_store:
            headers["cache-control"]="no-store, max-age=3600"
        body=b"<html><head><title>Flight physics</title></head><body>Aircraft dynamics source <a href='/next'>Next archive</a></body></html>"
        return FetchResponse(url,200,headers,body,time.time())

class CanonicalFreshnessTests(unittest.TestCase):
    def capture(self,no_store=False):
        at=time.time()
        fetcher=HTTPFetcher(no_store)
        run=CrawlRun.create(
            CrawlRequest(
                seed_urls=("https://example.com/source",),
                allowed_hosts=("example.com",),max_depth=1,
                max_requests=5,max_documents=2,
                max_response_bytes=65536,max_total_bytes=131072,
            ),
            scope={"tenant_id":"tenant","owner_id":"owner"},
            consent={"consent_id":"http-freshness-rights",
                     "capture_acknowledged":True,
                     "source_rights_acknowledged":True,
                     "expires_at":at+3600},
            now=at,fetcher=fetcher,
        )
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",return_value=at+offset):
                run.run_slice(max_steps=1,max_seconds=1,
                              authorize=lambda:None,cancelled=lambda:False,
                              on_checkpoint=lambda snap,event:None)
        return run,fetcher

    def test_canonical_capture_keeps_only_hashed_etag(self):
        run,fetcher=self.capture()
        state=run.snapshot()
        self.assertEqual(state["usage"]["requests"],2)
        self.assertEqual(state["usage"]["documents"],1)
        self.assertEqual(len(fetcher.calls),2)
        record=run.sources()[0]
        receipt=record["provenance"]["http_freshness"]
        self.assertIsNotNone(receipt["etag_digest"])
        self.assertNotIn("SECRET_ETAG",str(record))
        self.assertFalse(receipt["grants_new_consent"])
        self.assertFalse(record["provenance"]["training_permission"])
        self.assertEqual(record["review_state"],"unreviewed")
        self.assertEqual(CrawlRun.from_snapshot(state,fetcher=fetcher).snapshot(),state)

    def test_remote_no_store_prohibits_evidence_retention(self):
        run,fetcher=self.capture(no_store=True)
        state=run.snapshot()
        self.assertEqual(state["usage"]["requests"],2)
        self.assertEqual(state["usage"]["documents"],0)
        self.assertEqual(len(fetcher.calls),2)
        self.assertIn("https://example.com/next",[row["url"] for row in state["frontier"]])
        self.assertEqual(CrawlRun.from_snapshot(state,fetcher=fetcher).snapshot(),state)

if __name__=="__main__":
    unittest.main()
