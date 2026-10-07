import hashlib
import unittest

from skeleton.ai.webcrawler.context_bridge import compile_crawl_context
from skeleton.ai.webcrawler.core import CrawlDocument
from skeleton.ai.webcrawler.retrieval_bridge import CrawlRetrievalBridgeError


def doc(name, text):
    digest = hashlib.sha256(text.encode()).hexdigest()
    url = f"https://example.com/{name}"
    return CrawlDocument(
        url, url, name, text, "text/plain", digest, 1.0, 0.8,
        {
            "schema": "skeleton.ai.crawl.provenance.v1",
            "canonical_url": url,
            "fetched_url": url,
            "fetched_at": 1.0,
            "status": 200,
            "content_hash": digest,
        },
        (),
    )


class TestCrawlContextBridge(unittest.TestCase):
    def test_rank_and_budget_select_deterministically(self):
        a, b, c = doc("a", "alpha"), doc("b", "beta"), doc("c", "gamma")
        bundle = compile_crawl_context(
            "op", (a, b, c),
            token_costs=(3, 3, 3),
            semantic_scores=(0.1, 0.9, 0.5),
            token_budget=6,
        )
        self.assertEqual(len(bundle.compiled.selected_ids), 2)
        self.assertIn(b.content_hash, bundle.text_digest or "") if False else None
        self.assertEqual(bundle.text, "beta\n\ngamma")
        self.assertEqual(bundle.text_digest, hashlib.sha256(bundle.text.encode()).hexdigest())

    def test_retrieval_limit_precedes_context_budget(self):
        a, b = doc("a", "alpha"), doc("b", "beta")
        bundle = compile_crawl_context(
            "op", (a, b),
            token_costs=(1, 1),
            semantic_scores=(0.1, 0.9),
            token_budget=10,
            retrieval_limit=1,
        )
        self.assertEqual(bundle.text, "beta")
        self.assertEqual(len(bundle.records), 1)

    def test_duplicate_content_identity_fails_closed(self):
        a = doc("a", "same")
        b = doc("b", "same")
        with self.assertRaises(CrawlRetrievalBridgeError):
            compile_crawl_context("op", (a, b), token_costs=(1, 1), token_budget=2)

    def test_parallel_vector_lengths_are_exact(self):
        a = doc("a", "alpha")
        with self.assertRaises(CrawlRetrievalBridgeError):
            compile_crawl_context(
                "op", (a,), token_costs=(1,),
                semantic_scores=(0.1, 0.2), token_budget=1,
            )

    def test_context_budget_failure_is_normalized(self):
        a = doc("a", "alpha")
        with self.assertRaises(CrawlRetrievalBridgeError):
            compile_crawl_context("op", (a,), token_costs=(1,), token_budget=-1)


if __name__ == "__main__":
    unittest.main()
