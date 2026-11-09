import hashlib
import unittest
from dataclasses import replace

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig
from skeleton.ai.webcrawler.context_bridge import compile_crawl_context
from skeleton.ai.webcrawler.core import CrawlDocument
from skeleton.ai.webcrawler.generation_bridge import (
    EvidenceGenerationError,
    generate_from_crawl_context,
)
from skeleton.cortex.transformer import TinyTransformer


def document():
    text = "grounded evidence"
    digest = hashlib.sha256(text.encode()).hexdigest()
    url = "https://example.com/evidence"
    return CrawlDocument(
        url, url, "Evidence", text, "text/plain", digest, 1.0, 0.8,
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


class TestCrawlerNativeGenerationBridge(unittest.TestCase):
    def runtime(self):
        return NativeLLMRuntime(
            TinyTransformer(
                vocab=["<unk>", "grounded", "evidence"],
                dim=4, ctx=8, n_heads=1, n_layers=1, d_ff=8,
            )
        )

    def bundle(self):
        return compile_crawl_context(
            "op", (document(),), token_costs=(2,), semantic_scores=(0.9,),
            token_budget=4,
        )

    def test_context_identity_survives_native_generation(self):
        runtime = self.runtime()
        bundle = self.bundle()
        result = generate_from_crawl_context(
            runtime, bundle, GenerationConfig(max_new_tokens=1, seed=7)
        )
        self.assertEqual(result.receipt.context_source_digest, bundle.compiled.source_digest)
        self.assertEqual(result.receipt.context_text_digest, bundle.text_digest)
        self.assertEqual(result.receipt.model_identity_digest, runtime.model_identity.identity_digest)
        self.assertEqual(result.receipt.output_digest, result.generation.output_digest)
        self.assertEqual(result.receipt.replay_receipt_digest, result.generation.replay_receipt.digest)

    def test_mutated_context_payload_fails_before_model_execution(self):
        runtime = self.runtime()
        bundle = replace(self.bundle(), text="mutated")
        with self.assertRaises(EvidenceGenerationError):
            generate_from_crawl_context(
                runtime, bundle, GenerationConfig(max_new_tokens=1)
            )

    def test_generation_receipt_rejects_output_rebinding(self):
        result = generate_from_crawl_context(
            self.runtime(), self.bundle(), GenerationConfig(max_new_tokens=1)
        )
        with self.assertRaises(EvidenceGenerationError):
            replace(
                result,
                receipt=replace(result.receipt, output_digest="0" * 64),
            )


if __name__ == "__main__":
    unittest.main()
