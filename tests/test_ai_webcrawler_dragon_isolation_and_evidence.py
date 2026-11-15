"""Fault containment, exact alias replay and diverse retrieval regressions."""
from __future__ import annotations

import hashlib
import os
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.evidence_selection import select_diverse_evidence
from skeleton.ai.webcrawler.operations import CrawlOperationError, CrawlRun
from skeleton.ai.webcrawler.parser_isolation import (
    ParserFault, discover_isolated, extract_isolated, requires_isolation,
)
from test_ai_webcrawler_dragon_adaptive_instruction_guard import (
    BASE, OTHER, GOOD, ROBOTS, ScriptedFetcher, make_run, resign, step,
)


def hit(n, text, *, host="example.com", score=.9, content=None, start=0):
    return {
        "source_id": str(n), "content_hash": content or hashlib.sha256(str(n).encode()).hexdigest(),
        "canonical_url": "https://" + host + "/source-" + str(n),
        "passage_hash": hashlib.sha256(text.encode()).hexdigest(),
        "start": start, "end": start + len(text), "text": text, "lexical_score": score,
    }


class EvidenceSelectionTests(unittest.TestCase):
    def test_exact_duplicate_passages_never_fill_multiple_context_slots(self):
        a = hit(1, "Orbital mechanics and stable flight dynamics.")
        mirror = hit(2, a["text"], host="example.org", score=.89)
        distinct = hit(3, "The transfer orbit requires an independent velocity calculation.", score=.82)
        original = [mirror, distinct, a]
        selected = select_diverse_evidence(original, limit=3, distinct_sources=True)
        self.assertEqual(selected, [a, distinct])
        self.assertIs(selected[0], a)
        self.assertEqual(original, [mirror, distinct, a])

    def test_similar_but_distinct_numeric_evidence_is_not_discarded(self):
        a = hit(1, "The orbital experiment employed ten instruments and measured velocity 100.")
        b = hit(2, "The orbital experiment employed ten instruments and measured velocity 120.",
                host="example.org")
        c = hit(3, "Alternative trajectory analysis includes gravitational acceleration.", score=.88)
        selected = select_diverse_evidence([a, b, c], limit=3, distinct_sources=True)
        self.assertEqual({row["source_id"] for row in selected}, {"1", "2", "3"})
        self.assertEqual(selected[0], a)
        self.assertEqual(selected[1], c)

    def test_forged_passage_and_capacity_are_rejected(self):
        a = hit(1, "Orbital mechanics.")
        with self.assertRaises(ValueError):
            select_diverse_evidence([{**a, "text": "Altered evidence."}])
        with self.assertRaises(ValueError):
            select_diverse_evidence([a] * 513)


class ParserIsolationTests(unittest.TestCase):
    def test_complex_and_large_inputs_require_worker(self):
        self.assertTrue(requires_isolation("application/json", 100))
        self.assertTrue(requires_isolation("text/html", 65537))
        self.assertFalse(requires_isolation("text/plain", 1024))
        self.assertFalse(requires_isolation("application/pdf", 1024))

    @unittest.skipUnless(os.name == "posix", "requires hard POSIX worker resource limits")
    def test_real_disposable_document_child(self):
        body = b"# Orbital mechanics\n\nReliable source content."
        response = FetchResponse(BASE + "/source.md", 200, {"content-type": "text/markdown"},
                                 body, time.time())
        outcome = extract_isolated(response, response.url, max_chars=4096,
                                   deadline=time.monotonic() + 8)
        self.assertIsNotNone(outcome.document)
        doc = outcome.document
        self.assertIn("Orbital mechanics", doc.text)
        self.assertEqual(doc.provenance["raw_body_hash"], hashlib.sha256(body).hexdigest())
        self.assertEqual(doc.provenance["parser_execution"], "isolated_posix")
        self.assertEqual(doc.content_hash, hashlib.sha256(doc.text.encode()).hexdigest())

    @unittest.skipUnless(os.name == "posix", "requires hard POSIX worker resource limits")
    def test_real_structured_child_returns_only_discovery(self):
        body = (b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                b'<url><loc>https://example.com/orbit</loc></url>'
                b'<url><loc>https://private.example/denied</loc></url></urlset>')
        result = discover_isolated(body, media_type="application/xml",
                                  document_url=BASE + "/sitemap.xml",
                                  allowed_hosts=frozenset({"example.com"}),
                                  max_bytes=4096, deadline=time.monotonic() + 8)
        self.assertEqual(result.links, (BASE + "/orbit",))
        self.assertFalse(result.source_text_retained)
        self.assertFalse(result.new_authority_granted)

    def test_deadline_fault_settles_bytes_and_continues_next_source(self):
        first, second = BASE + "/first", BASE + "/second"
        body = b"# Orbital mechanics\n\nReference notes."
        fetcher = ScriptedFetcher({
            BASE + "/robots.txt": (200, "text/plain", ROBOTS, {}),
            first: (200, "text/markdown", body, {}),
            second: (200, "text/html", GOOD, {}),
        })
        run, at = make_run(fetcher, seeds=(first, second), depth=0)
        step(run, at + 1)
        with patch("skeleton.ai.webcrawler.operations.extract_isolated",
                   side_effect=ParserFault("deadline")):
            result = step(run, at + 2)
        self.assertEqual(result["slice_events"][0]["reason"], "document_parser_deadline")
        self.assertEqual(run.snapshot()["usage"]["bytes"], len(ROBOTS) + len(body))
        self.assertEqual(run.snapshot()["usage"]["reserved_bytes"], 0)
        restored = CrawlRun.from_snapshot(run.snapshot(), fetcher=fetcher)
        step(restored, at + 3)
        self.assertEqual(restored.status()["source_count"], 1)
        self.assertEqual([url for url, _ in fetcher.calls].count(first), 1)


class DurableAliasTests(unittest.TestCase):
    def test_duplicate_capture_keeps_exact_provenance_without_second_document(self):
        first, another = BASE + "/first", OTHER + "/mirror"
        fetcher = ScriptedFetcher({
            BASE + "/robots.txt": (200, "text/plain", ROBOTS, {}),
            OTHER + "/robots.txt": (200, "text/plain", ROBOTS, {}),
            first: (200, "text/html", GOOD, {}),
            another: (200, "text/html", GOOD, {}),
        })
        run, at = make_run(fetcher, seeds=(first, another), depth=0)
        for i in range(1, 8):
            step(run, at + i)
        snap = run.snapshot()
        self.assertEqual(snap["usage"]["documents"], 1)
        self.assertEqual(len(snap["source_aliases"]), 1)
        alias = snap["source_aliases"][0]
        self.assertEqual(alias["canonical_url"], another)
        self.assertFalse(alias["independent_evidence"])
        restored = CrawlRun.from_snapshot(snap, fetcher=fetcher)
        self.assertEqual(restored.source_aliases(alias["source_id"]), [alias])
        self.assertEqual(restored.status()["duplicate_evidence"]["count"], 1)
        snap["source_aliases"][0]["independent_evidence"] = True
        with self.assertRaises(CrawlOperationError):
            CrawlRun.from_snapshot(resign(snap), fetcher=fetcher)


if __name__ == "__main__":
    unittest.main()
