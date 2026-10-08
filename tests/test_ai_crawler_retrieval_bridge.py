import unittest
from dataclasses import replace

from skeleton.ai.webcrawler.core import CrawlDocument
from skeleton.ai.webcrawler.governance import PromotionDecision
from skeleton.ai.webcrawler.ingestion import IngestionReceipt
from skeleton.ai.webcrawler.evidence_retrieval_bridge import (
    CrawlRetrievalBridgeError,
    bridge_crawl_document,
)


class TestCrawlerRetrievalBridge(unittest.TestCase):
    def document(self):
        text = "retrieval evidence"
        import hashlib
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        provenance = {
            "schema": "skeleton.ai.crawl.provenance.v1",
            "canonical_url": "https://example.com/source",
            "fetched_url": "https://example.com/source",
            "fetched_at": 100.0,
            "status": 200,
            "content_hash": digest,
        }
        return CrawlDocument(
            canonical_url="https://example.com/source",
            fetched_url="https://example.com/source",
            title="Source",
            text=text,
            content_type="text/plain",
            content_hash=digest,
            fetched_at=100.0,
            source_score=0.8,
            provenance=provenance,
            links=(),
        )

    def test_verified_document_enters_canonical_retrieval_and_context(self):
        record = bridge_crawl_document(
            self.document(),
            lexical_score=0.25,
            semantic_score=0.75,
            freshness_score=0.9,
            token_cost=4,
            priority=10,
        )
        self.assertEqual(record.candidate.content_digest, self.document().content_hash)
        self.assertEqual(record.candidate.semantic_ppm, 750000)
        self.assertEqual(record.context_item.kind, "external-crawl-data")
        self.assertFalse(record.context_item.mandatory)
        self.assertEqual(record.context_item.provenance_digest, record.provenance_digest)

    def test_external_crawl_data_never_becomes_mandatory_instruction(self):
        record = bridge_crawl_document(self.document(), token_cost=1)
        self.assertFalse(record.context_item.mandatory)
        self.assertEqual(record.context_item.kind, "external-crawl-data")

    def test_content_tampering_fails_closed(self):
        with self.assertRaises(CrawlRetrievalBridgeError):
            bridge_crawl_document(replace(self.document(), text="tampered"), token_cost=1)

    def test_provenance_url_rebinding_fails_closed(self):
        doc = self.document()
        provenance = dict(doc.provenance)
        provenance["canonical_url"] = "https://evil.example/rebound"
        with self.assertRaises(CrawlRetrievalBridgeError):
            bridge_crawl_document(replace(doc, provenance=provenance), token_cost=1)

    def test_failed_http_status_fails_closed(self):
        doc = self.document()
        provenance = dict(doc.provenance)
        provenance["status"] = 500
        with self.assertRaises(CrawlRetrievalBridgeError):
            bridge_crawl_document(replace(doc, provenance=provenance), token_cost=1)

    def test_schema_drift_fails_closed(self):
        doc = self.document()
        provenance = dict(doc.provenance)
        provenance["schema"] = "unknown"
        with self.assertRaises(CrawlRetrievalBridgeError):
            bridge_crawl_document(replace(doc, provenance=provenance), token_cost=1)

    def test_scores_are_bounded_and_boolean_confusion_rejected(self):
        with self.assertRaises(CrawlRetrievalBridgeError):
            bridge_crawl_document(self.document(), semantic_score=1.01, token_cost=1)
        with self.assertRaises(CrawlRetrievalBridgeError):
            bridge_crawl_document(self.document(), lexical_score=True, token_cost=1)

    def test_token_budget_type_confusion_rejected(self):
        with self.assertRaises(CrawlRetrievalBridgeError):
            bridge_crawl_document(self.document(), token_cost=True)


    def test_governed_promotion_is_bound_to_exact_content(self):
        doc = self.document()
        promotion = PromotionDecision(
            "d" * 64, doc.content_hash, "promote", (), 101.0, 0.9,
            "skeleton.ai.crawl.provenance.v1",
        )
        record = bridge_crawl_document(doc, token_cost=1, promotion=promotion)
        self.assertEqual(record.candidate.content_digest, doc.content_hash)

    def test_quarantined_content_cannot_enter_retrieval(self):
        doc = self.document()
        decision = PromotionDecision(
            "d" * 64, doc.content_hash, "quarantine", ("low_assurance",),
            101.0, 0.1, "skeleton.ai.crawl.provenance.v1",
        )
        with self.assertRaises(CrawlRetrievalBridgeError):
            bridge_crawl_document(doc, token_cost=1, promotion=decision)

    def test_promotion_rebinding_and_schema_drift_fail_closed(self):
        doc = self.document()
        wrong_content = PromotionDecision(
            "d" * 64, "0" * 64, "promote", (), 101.0, 0.9,
            "skeleton.ai.crawl.provenance.v1",
        )
        with self.assertRaises(CrawlRetrievalBridgeError):
            bridge_crawl_document(doc, token_cost=1, promotion=wrong_content)
        wrong_schema = PromotionDecision(
            "d" * 64, doc.content_hash, "promote", (), 101.0, 0.9, "other",
        )
        with self.assertRaises(CrawlRetrievalBridgeError):
            bridge_crawl_document(doc, token_cost=1, promotion=wrong_schema)


    def test_accepted_ingestion_receipt_binds_exact_promoted_document(self):
        doc = self.document()
        promotion = PromotionDecision(
            "d" * 64, doc.content_hash, "promote", (), 101.0, 0.9,
            "skeleton.ai.crawl.provenance.v1",
        )
        ingestion = IngestionReceipt(doc.content_hash, "retrieval", True, "promoted")
        record = bridge_crawl_document(
            doc, token_cost=1, promotion=promotion, ingestion=ingestion
        )
        self.assertEqual(record.candidate.content_digest, ingestion.content_hash)

    def test_ingestion_receipt_rebinding_fails_closed(self):
        doc = self.document()
        promotion = PromotionDecision(
            "d" * 64, doc.content_hash, "promote", (), 101.0, 0.9,
            "skeleton.ai.crawl.provenance.v1",
        )
        cases = (
            IngestionReceipt("0" * 64, "retrieval", True, "promoted"),
            IngestionReceipt(doc.content_hash, "training", True, "promoted"),
            IngestionReceipt(doc.content_hash, "retrieval", False, "not_promoted"),
        )
        for receipt in cases:
            with self.subTest(receipt=receipt):
                with self.assertRaises(CrawlRetrievalBridgeError):
                    bridge_crawl_document(
                        doc, token_cost=1, promotion=promotion, ingestion=receipt
                    )

    def test_accepted_ingestion_without_promotion_evidence_fails_closed(self):
        doc = self.document()
        receipt = IngestionReceipt(doc.content_hash, "retrieval", True, "promoted")
        with self.assertRaises(CrawlRetrievalBridgeError):
            bridge_crawl_document(doc, token_cost=1, ingestion=receipt)


if __name__ == "__main__":
    unittest.main()
