import unittest
from dataclasses import replace

from skeleton.ai.webcrawler.core import CrawlDocument
from skeleton.ai.webcrawler.retrieval_bridge import (
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


if __name__ == "__main__":
    unittest.main()
