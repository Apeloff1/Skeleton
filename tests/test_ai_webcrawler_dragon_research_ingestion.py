"""Actual canonical worker capture and replay for external research formats."""
from __future__ import annotations

import json
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import FetchResponse, CrawlPolicy, extract_document
from skeleton.ai.webcrawler.operations import CrawlRun, CrawlRequest

CASES = (
    ("text/vtt", "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nWing loading\n",
     "Wing loading"),
    ("application/x-subrip",
     "1\n00:00:01,000 --> 00:00:02,000\nFlight stability\n",
     "Flight stability"),
    ("text/calendar", "BEGIN:VCALENDAR\nBEGIN:VEVENT\n"
     "SUMMARY:Aircraft symposium\nDTSTART;VALUE=DATE:20261107\n"
     "ATTENDEE:mailto:secret@example.com\n"
     "END:VEVENT\nEND:VCALENDAR", "Aircraft symposium"),
    ("application/x-research-info-systems",
     "TY  - JOUR\nTI  - Stability of flight models\n"
     "AU  - Researcher\nER  -\n", "Stability of flight models"),
    ("application/x-bibtex", "@article{one,title={Aircraft stability}}",
     "Aircraft stability"),
    ("application/x-ipynb+json",
     json.dumps({"nbformat":4,"cells":[{"cell_type":"markdown",
             "source":"# Original flight notebook"}]}), "Original flight notebook"),
    ("application/n-triples",
     '<https://example.com/a> <https://schema.org/name> "Flight machine" .',
     "Flight machine"),
    ("application/n-quads",
     '<https://example.com/a> <https://schema.org/name> "Flight machine" '
     '<https://example.com/graph> .', "Flight machine"),
)


class FakeFetcher:
    timeout_seconds = 4
    transport_mode = "scripted_research_artifact_canonical_transport"

    def __init__(self, media_type, text):
        self.media_type = media_type
        self.body = text.encode("utf-8")
        self.calls = []

    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        if url == "https://example.com/robots.txt":
            return FetchResponse(
                url, 200, {"content-type":"text/plain"},
                b"User-agent: *\nAllow: /\n", time.time(),
            )
        if url != "https://example.com/research":
            raise AssertionError("artifact generated an unauthorized target")
        if len(self.body) > max_bytes:
            raise AssertionError("transport request exceeded byte reservation")
        return FetchResponse(
            url, 200, {"content-type":self.media_type}, self.body, time.time(),
        )


class CanonicalResearchArtifactTests(unittest.TestCase):
    def run_artifact(self, mime, text):
        now = time.time()
        fetcher = FakeFetcher(mime, text)
        run = CrawlRun.create(
            CrawlRequest(
                seed_urls=("https://example.com/research",),
                allowed_hosts=("example.com",),
                query="flight aircraft research",
                max_depth=1, max_requests=4, max_documents=2,
                max_response_bytes=65536, max_total_bytes=131072,
            ),
            scope={"tenant_id":"tenant", "owner_id":"owner"},
            consent={
                "consent_id":"research-artifacts-rights",
                "capture_acknowledged":True,
                "source_rights_acknowledged":True,
                "expires_at":now+3600,
            },
            now=now, fetcher=fetcher,
        )
        for second in (1, 3):
            with patch("skeleton.ai.webcrawler.operations.time.time",
                       return_value=now+second):
                run.run_slice(
                    max_steps=1, max_seconds=1,
                    authorize=lambda:None,
                    cancelled=lambda:False,
                    on_checkpoint=lambda snapshot,event:None,
                )
        return run, fetcher

    def test_real_worker_source_capture_and_replay_each_mime(self):
        for mime, source, expected in CASES:
            with self.subTest(mime=mime):
                run, fetcher = self.run_artifact(mime, source)
                snapshot = run.snapshot()
                self.assertEqual(snapshot["usage"]["documents"], 1)
                self.assertEqual(snapshot["usage"]["requests"], 2)
                self.assertEqual(snapshot["frontier"], [])
                self.assertEqual(set(fetcher.calls), {
                    "https://example.com/robots.txt",
                    "https://example.com/research",
                })
                self.assertEqual(len(fetcher.calls), 2)
                result = run.sources()[0]
                self.assertIn(expected, result["text"])
                self.assertEqual(result["content_type"], mime)
                self.assertEqual(result["review_state"], "unreviewed")
                self.assertFalse(result["provenance"]["training_permission"])
                self.assertFalse(result["provenance"]["raw_bytes_retained"])
                self.assertEqual(
                    CrawlRun.from_snapshot(snapshot, fetcher=fetcher).snapshot(),
                    snapshot,
                )

    def test_bad_calendar_consumes_request_without_evidence(self):
        run, fetcher = self.run_artifact(
            "text/calendar", "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:broken",
        )
        self.assertEqual(run.snapshot()["usage"]["documents"], 0)
        self.assertEqual(len(fetcher.calls), 2)
        self.assertEqual(run.snapshot()["frontier"], [])

    def test_bibtex_macros_do_not_publish_evidence(self):
        run, _ = self.run_artifact(
            "application/x-bibtex", "@article{one,title=untrusted_macro}",
        )
        self.assertEqual(run.snapshot()["usage"]["documents"], 0)

    def test_invitees_and_outputs_cannot_enter_retained_evidence(self):
        run, _ = self.run_artifact("text/calendar", CASES[2][1])
        self.assertNotIn("secret@example.com", run.sources()[0]["text"])
        run, _ = self.run_artifact(
            "application/x-ipynb+json",
            json.dumps({"nbformat":4, "metadata":{"private":"SECRET"},
                "cells":[{"cell_type":"markdown","source":"Flight research",
                          "outputs":[{"text":"SECRET_OUTPUT"}]}]}),
        )
        self.assertNotIn("SECRET", run.sources()[0]["text"])

    def test_source_urls_cannot_create_extra_dispatch(self):
        run, fetcher = self.run_artifact(
            "text/calendar", "BEGIN:VCALENDAR\nBEGIN:VEVENT\n"
            "SUMMARY:https://outside.example.net/private\n"
            "END:VEVENT\nEND:VCALENDAR",
        )
        self.assertEqual(run.snapshot()["usage"]["documents"], 1)
        self.assertEqual(len(fetcher.calls), 2)

    def test_strict_utf8_rejection(self):
        response = FetchResponse(
            "https://example.com/research", 200,
            {"content-type":"text/calendar"}, b"\xff\xfe", time.time(),
        )
        with self.assertRaises(ValueError):
            extract_document(response, response.url, max_text_chars=1024)

    def test_mime_denial_does_not_widen_policy(self):
        policy = CrawlPolicy(allowed_hosts=frozenset({"example.com"}))
        self.assertIn("text/vtt", policy.allowed_content_types)
        self.assertNotIn("application/x-executable", policy.allowed_content_types)


if __name__ == "__main__":
    unittest.main()
