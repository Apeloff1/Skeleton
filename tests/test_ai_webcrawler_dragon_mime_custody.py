"""Adversarial legacy and extended MIME custody contracts.

These are source-only checks, with no Mongo, DNS, HTTP, model, or device I/O.
The snapshot fixture is deliberately rehashed after every mutation so failures
test the MIME policy itself rather than a stale top-level digest.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import unittest

from skeleton.ai.webcrawler.core import CrawlDocument, _source_score
from skeleton.ai.webcrawler.dragon_campaign_stack.contracts import digest
from skeleton.ai.webcrawler.operations import CrawlOperationError, CrawlRun
from skeleton.ai.webcrawler.research import EvidenceObservation
from test_ai_webcrawler_dragon_atlas import DragonAtlasRegression, research_text


class DragonMimeCustodyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = DragonAtlasRegression(
            methodName="test_empty_atlas_review_only_and_trace_valid",
        )
        self.fixture.setUp()
        self.original = self.fixture.with_sources(
            ("https://example.com/archive", research_text("mime")),
        )

    def _snapshot(self, *, effective_type=None, **provenance):
        snapshot = deepcopy(self.original)
        source = next(iter(snapshot["sources"].values()))
        if effective_type is not None:
            source["content_type"] = effective_type
        source["provenance"].update(provenance)
        document = CrawlDocument(
            canonical_url=source["canonical_url"],
            fetched_url=source["fetched_url"],
            title=source["title"],
            text=source["text"],
            content_type=source["content_type"],
            content_hash=source["content_hash"],
            fetched_at=source["fetched_at"],
            source_score=_source_score(
                source["canonical_url"], source["text"],
                source["provenance"]["status"],
            ),
            provenance=source["provenance"],
            links=(),
        )
        source["observation"] = asdict(
            EvidenceObservation.from_document(document, self.fixture.request.query),
        )
        snapshot["snapshot_digest"] = digest(
            {key: value for key, value in snapshot.items() if key != "snapshot_digest"},
        )
        return snapshot

    def _denied(self, **changes):
        with self.assertRaisesRegex(
            CrawlOperationError, "source MIME inference receipt mismatch",
        ):
            CrawlRun.from_snapshot(self._snapshot(**changes))

    def test_legacy_without_any_mime_extension_still_loads(self):
        self.assertEqual(
            CrawlRun.from_snapshot(self.original).snapshot()["snapshot_digest"],
            self.original["snapshot_digest"],
        )

    def test_full_declared_text_receipt_loads(self):
        snapshot = self._snapshot(
            mime_inferred=False,
            declared_content_type="text/plain",
            mime_inference_reason="declared_media_kept",
        )
        self.assertEqual(
            CrawlRun.from_snapshot(snapshot).snapshot()["snapshot_digest"],
            snapshot["snapshot_digest"],
        )

    def test_complete_bounded_pdf_inference_receipt_loads(self):
        snapshot = self._snapshot(
            effective_type="application/pdf",
            mime_inferred=True,
            declared_content_type="application/octet-stream",
            mime_inference_reason="pdf_magic_and_extension",
        )
        self.assertEqual(
            CrawlRun.from_snapshot(snapshot).snapshot()["snapshot_digest"],
            snapshot["snapshot_digest"],
        )

    def test_every_partial_receipt_is_denied(self):
        cases = (
            {"mime_inferred": False},
            {"declared_content_type": "text/plain"},
            {"mime_inference_reason": "declared_media_kept"},
            {"mime_inferred": False, "declared_content_type": "text/plain"},
            {"mime_inferred": False, "mime_inference_reason": "declared_media_kept"},
            {"declared_content_type": "text/plain", "mime_inference_reason": "declared_media_kept"},
        )
        for fields in cases:
            with self.subTest(fields=fields):
                self._denied(**fields)

    def test_python_integer_cannot_impersonate_boolean(self):
        self._denied(
            mime_inferred=1,
            declared_content_type="text/plain",
            mime_inference_reason="declared_media_kept",
        )

    def test_non_inferred_receipt_cannot_change_declared_type(self):
        self._denied(
            mime_inferred=False,
            declared_content_type="application/octet-stream",
            mime_inference_reason="declared_media_kept",
        )

    def test_unrecognized_reason_does_not_become_source_authority(self):
        self._denied(
            mime_inferred=False,
            declared_content_type="text/plain",
            mime_inference_reason="injected_policy_override",
        )

    def test_inferred_boolean_cannot_claim_declared_text(self):
        self._denied(
            mime_inferred=True,
            declared_content_type="text/plain",
            mime_inference_reason="pdf_magic_and_extension",
        )

    def test_inferred_pdf_reason_cannot_promote_plain_text(self):
        self._denied(
            mime_inferred=True,
            declared_content_type="application/octet-stream",
            mime_inference_reason="pdf_magic_and_extension",
        )

    def test_mismatched_magic_family_reason_is_denied(self):
        self._denied(
            effective_type="application/pdf",
            mime_inferred=True,
            declared_content_type="application/octet-stream",
            mime_inference_reason="finite_xml_prefix_and_extension",
        )

    def test_missing_reason_is_not_a_legacy_receipt(self):
        self._denied(
            mime_inferred=False,
            declared_content_type="text/plain",
        )

    def test_oversized_declared_type_is_denied(self):
        self._denied(
            mime_inferred=False,
            declared_content_type="x" * 257,
            mime_inference_reason="declared_media_kept",
        )

    def test_unknown_reason_type_is_denied(self):
        self._denied(
            mime_inferred=False,
            declared_content_type="text/plain",
            mime_inference_reason=17,
        )


if __name__ == "__main__":
    unittest.main()
