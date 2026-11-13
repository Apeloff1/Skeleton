"""duplicate_filter: original-byte, vector and scope-bound retrieval tests."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import CognitionError
from skeleton.ai.runtime.operational_ai.offline_cognition.core.sources import bind_source
from skeleton.ai.runtime.operational_ai.offline_cognition.core.evidence_pipeline import EvidenceDocument
from skeleton.ai.runtime.operational_ai.offline_cognition.families.duplicate_filter import evidence
MODEL="a"*64

class DuplicateFilterEvidenceTests(unittest.TestCase):
    def setUp(self):
        raw=("Original offline source café ☃ bounded evidence citation. "*4).encode("utf-8")
        receipt=bind_source(raw,source_id="doc",tenant="local",subject="owner",approved=True)
        self.doc=EvidenceDocument(receipt,raw,(1.,0.),MODEL)
        self.catalog=evidence.index((self.doc,),tenant="local",subject="owner")

    def test_unicode_byte_offsets(self):
        spans=evidence.passages(self.doc,window_bytes=32,overlap_bytes=8)
        self.assertGreater(len(spans),1)
        self.assertTrue(all(evidence.citation(self.catalog,s)["exact_bytes_verified"] for s in spans))

    def test_source_retrieval_with_real_vector_when_required(self):
        supplied={} if evidence.contract()["mode"]=="lexical" else {"query_vector":(1.,0.),"embedding_model_sha256":MODEL}
        results=evidence.query(self.catalog,"offline",**supplied)
        self.assertEqual(results[0]["source_id"],"doc")
        self.assertFalse(results[0]["native_inference_executed"])

    def test_bad_vector_is_never_silently_replaced(self):
        if evidence.contract()["mode"]=="lexical":
            with self.assertRaises(CognitionError):
                evidence.query(self.catalog,"offline",query_vector=(1.,0.))
        else:
            with self.assertRaises(CognitionError):
                evidence.query(self.catalog,"offline")

    def test_invalid_overlap_still_fails_closed(self):
        with self.assertRaisesRegex(CognitionError, "overlap"):
            evidence.passages(self.doc, window_bytes=32, overlap_bytes=128)

    def test_attribution_not_semantic_claim(self):
        span=evidence.passages(self.doc,window_bytes=32,overlap_bytes=8)[0]
        result=evidence.report(self.catalog,(span,))
        self.assertEqual(result["schema"],"offline-source-attribution.v1")
        self.assertFalse(result["semantic_entailment_proved"])

    def test_deterministic_ranking(self):
        span=evidence.passages(self.doc,window_bytes=32,overlap_bytes=8)[0]
        self.assertEqual(evidence.rank_candidates(((span,0.8),)),(span,))

if __name__=="__main__":
    unittest.main()
