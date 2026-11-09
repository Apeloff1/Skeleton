"""Canonical WARC, HAR, CSL and patch acquisition plus adversarial redaction."""
from __future__ import annotations

import json
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import FetchResponse, extract_document, CrawlPolicy
from skeleton.ai.webcrawler.operations import CrawlRun, CrawlRequest
from skeleton.ai.webcrawler.research_projection import ResearchFormatError
from skeleton.ai.webcrawler.warc_catalog import extract_warc_catalog
from skeleton.ai.webcrawler.har_documents import extract_har
from skeleton.ai.webcrawler.patch_documents import extract_unified_patch
from skeleton.ai.webcrawler.csl_documents import extract_csl

PAYLOAD = (b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
           b"Authorization: Bearer SUPERSECRET_BODY")
WARC = (
    b"WARC/1.1\r\nWARC-Type: response\r\n"
    b"WARC-Target-URI: https://outside.example.net/private?api_key=SUPERSECRET_URL\r\n"
    b"WARC-Date: 2026-11-07T00:00:00Z\r\n"
    b"Content-Length: " + str(len(PAYLOAD)).encode() + b"\r\n\r\n" + PAYLOAD
)
HAR = json.dumps({"log": {"version":"1.2","creator":{"name":"ignored"},
    "entries":[
        {"request":{"method":"GET","url":"https://outside.example.net/private?secret=SECRETHAR",
            "headers":[{"name":"Authorization","value":"SECRET_HEADER"}],
            "cookies":[{"name":"token","value":"SECRET_COOKIE"}]},
         "response":{"status":200,"content":{"mimeType":"text/html;charset=UTF-8",
             "size":443,"text":"SECRET_RESPONSE"}},
         "time":12.5},
        {"request":{"method":"POST", "postData":{"text":"SECRET_POSTBODY"}},
         "response":{"status":201,"content":{"size":5,"mimeType":"application/json"}},
         "time":40.25}
    ]}})
PATCH = ("diff --git a/src/flight.py b/src/flight.py\n"
         "index 1111111..2222222 100644\n"
         "--- a/src/flight.py\n+++ b/src/flight.py\n"
         "@@ -1,2 +1,3 @@\n"
         "-old_flight = True\n"
         "+lift = 12\n"
         "+api_key = 'SECRET_PATCH_TOKEN'\n"
         "diff --git a/.env b/.env\n"
         "--- a/.env\n+++ b/.env\n"
         "@@ -1 +1 @@\n"
         "+SUPER_SECRET_ENV=secret\n")
CSL = json.dumps([
    {"id":"a","title":"Wing loading and archive studies","type":"article-journal",
     "author":[{"given":"Ada","family":"Researcher"}],
     "issued":{"date-parts":[[2026,11,7]]},"DOI":"10.1234/original",
     "URL":"https://outside.example.net/DOI?secret=SECRET_CSL"},
    {"id":"b","title":"Aerodynamics handbook", "publisher":"Original archive"}
])


class ArchiveSourceParserTests(unittest.TestCase):
    def test_warc_metadata_only_and_no_secrets(self):
        row = extract_warc_catalog(WARC)
        self.assertIn("type: response", row.text)
        self.assertIn("payload_sha256:", row.text)
        self.assertNotIn("SUPERSECRET", row.text)
        self.assertNotIn("outside.example.net", row.text)
        self.assertEqual(row.links, ())
        self.assertFalse(row.body_executed)

    def test_warc_record_length_framing_denied_if_truncated(self):
        with self.assertRaises(ResearchFormatError):
            extract_warc_catalog(WARC[:-2])

    def test_warc_duplicate_content_length_denied(self):
        malicious = WARC.replace(b"Content-Length:", b"Content-Length: 1\r\nContent-Length:")
        with self.assertRaises(ResearchFormatError):
            extract_warc_catalog(malicious)

    def test_warc_record_limit(self):
        with self.assertRaises(ResearchFormatError):
            extract_warc_catalog((WARC + b"\r\n\r\n")*129)

    def test_har_minimal_performance_not_credentials(self):
        row = extract_har(HAR)
        self.assertIn("elapsed_ms: 12.500", row.text)
        self.assertIn("status: 201", row.text)
        for secret in ("SECRETHAR", "SECRET_HEADER", "SECRET_COOKIE",
                       "SECRET_RESPONSE", "SECRET_POSTBODY", "outside.example.net"):
            self.assertNotIn(secret, row.text)
        self.assertEqual(row.links, ())

    def test_har_duplicate_fields_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_har('{"log":{"entries":[],"entries":[]}}')

    def test_har_nonfinite_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_har('{"log":{"entries":[{"time":NaN}]}}')

    def test_har_unbounded_entries_denied(self):
        many = json.dumps({"log":{"entries":[{}]*257}})
        with self.assertRaises(ResearchFormatError):
            extract_har(many)

    def test_patch_lines_credential_redacted(self):
        row = extract_unified_patch(PATCH)
        self.assertIn("lift = 12", row.text)
        self.assertIn("credential-related patch line withheld", row.text)
        self.assertNotIn("SECRET_PATCH_TOKEN", row.text)
        self.assertNotIn("SUPER_SECRET_ENV", row.text)
        self.assertEqual(row.links, ())

    def test_binary_patch_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_unified_patch(PATCH+"GIT binary patch\nliteral 20\n")

    def test_invalid_hunk_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_unified_patch(PATCH.replace("@@ -1,2 +1,3 @@", "@@ corrupted @@"))

    def test_path_traversal_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_unified_patch(PATCH.replace("b/src/flight.py", "b/../../etc/passwd"))

    def test_csl_citation_without_links(self):
        row = extract_csl(CSL)
        self.assertIn("Wing loading", row.text)
        self.assertIn("Researcher", row.text)
        self.assertIn("2026-11-7", row.text)
        self.assertIn("Aerodynamics handbook", row.text)
        self.assertNotIn("outside.example.net", row.text)
        self.assertNotIn("SECRET_CSL", row.text)
        self.assertEqual(row.links, ())

    def test_csl_bad_author_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_csl('{"title":"Test","author":[42]}')

    def test_csl_duplicate_field_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_csl('{"title":"One","title":"Two"}')


class ResearchFetcher:
    timeout_seconds = 4
    transport_mode = "scripted_technical_research"
    def __init__(self, mime, data):
        self.mime, self.data, self.calls = mime, data, []
    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        if url == "https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url != "https://example.com/evidence":
            raise AssertionError("untrusted research artifact requested an extra URL")
        if len(self.data)>max_bytes:
            raise AssertionError("scripted transport budget exceeded")
        return FetchResponse(url,200,{"content-type":self.mime},self.data,time.time())


class CanonicalArchiveIngestionTests(unittest.TestCase):
    def run_source(self, mime, raw):
        now = time.time()
        fetcher = ResearchFetcher(mime,raw)
        run = CrawlRun.create(
            CrawlRequest(
                seed_urls=("https://example.com/evidence",),allowed_hosts=("example.com",),
                max_requests=4,max_documents=2,max_depth=1,
                max_response_bytes=65536,max_total_bytes=131072,
            ),
            scope={"tenant_id":"tenant","owner_id":"owner"},
            consent={"consent_id":"archive-source-rights",
                     "capture_acknowledged":True,
                     "source_rights_acknowledged":True,
                     "expires_at":now+3600},
            now=now,fetcher=fetcher,
        )
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",
                       return_value=now+offset):
                run.run_slice(max_steps=1,max_seconds=1,
                              authorize=lambda:None,cancelled=lambda:False,
                              on_checkpoint=lambda snapshot,event:None)
        return run,fetcher

    def test_real_canonical_worker_formats_and_replay(self):
        samples=(
            ("application/warc",WARC,"payload_sha256"),
            ("application/har+json",HAR.encode(),"elapsed_ms"),
            ("text/x-diff",PATCH.encode(),"lift = 12"),
            ("application/vnd.citationstyles.csl+json",CSL.encode(),"Wing loading"),
        )
        for mime,raw,expected in samples:
            with self.subTest(mime=mime):
                run,fetcher=self.run_source(mime,raw)
                snap=run.snapshot()
                self.assertEqual(snap["usage"]["documents"],1)
                self.assertEqual(snap["usage"]["requests"],2)
                self.assertEqual(snap["frontier"],[])
                self.assertEqual(len(fetcher.calls),2)
                self.assertIn(expected,run.sources()[0]["text"])
                self.assertEqual(run.sources()[0]["review_state"],"unreviewed")
                self.assertFalse(run.sources()[0]["provenance"]["training_permission"])
                self.assertEqual(
                    CrawlRun.from_snapshot(snap,fetcher=fetcher).snapshot(),snap,
                )

    def test_malformed_warc_charged_but_not_retained(self):
        run,fetcher=self.run_source("application/warc",WARC[:-3])
        self.assertEqual(run.snapshot()["usage"]["documents"],0)
        self.assertEqual(len(fetcher.calls),2)

    def test_credentials_not_retained_by_actual_worker(self):
        for mime,raw,secret in (
            ("application/har+json",HAR.encode(),"SECRET_HEADER"),
            ("text/x-diff",PATCH.encode(),"SECRET_PATCH_TOKEN"),
            ("application/warc",WARC,"SUPERSECRET_BODY"),
        ):
            with self.subTest(mime=mime):
                run,_=self.run_source(mime,raw)
                self.assertNotIn(secret,run.sources()[0]["text"])

    def test_exact_new_media_allowlist(self):
        allowed=CrawlPolicy(allowed_hosts=frozenset({"example.com"})).allowed_content_types
        for mime in ("application/warc","application/har+json",
                     "text/x-diff","application/vnd.citationstyles.csl+json"):
            self.assertIn(mime,allowed)


if __name__=="__main__":
    unittest.main()
