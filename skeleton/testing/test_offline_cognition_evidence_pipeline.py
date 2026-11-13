"""Real bounded offline evidence algorithms with hostile negative cases."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import CognitionError
from skeleton.ai.runtime.operational_ai.offline_cognition.core.sources import bind_source
from skeleton.ai.runtime.operational_ai.offline_cognition.core.evidence_pipeline import (
    EvidenceDocument,EvidenceSpan,EvidenceIndex,partition,verify,unique_spans,diverse_spans,
)
MODEL="a"*64

def make(name,raw,tenant="local",subject="owner",approved=True,model=MODEL):
    source=bind_source(raw,source_id=name,tenant=tenant,subject=subject,approved=approved)
    return EvidenceDocument(source,raw,(1.,0.),model)

class EvidencePipelineTests(unittest.TestCase):
    def setUp(self):
        self.a=make("a","original ☃ source evidence offline runtime".encode())
        self.b=make("b",b"offline model source rights citation")
        self.index=EvidenceIndex((self.a,self.b),tenant="local",subject="owner")

    def test_lexical(self):
        self.assertEqual(self.index.lexical("original")[0][0],"a")

    def test_dense_requires_exact_model(self):
        self.assertEqual(len(self.index.dense((1.,0.),embedding_model_sha256=MODEL)),2)
        with self.assertRaises(CognitionError):
            self.index.dense((1.,0.),embedding_model_sha256="b"*64)

    def test_dense_rejects_wrong_vector_shape(self):
        with self.assertRaises(CognitionError):
            self.index.dense((1.,0.,0.),embedding_model_sha256=MODEL)

    def test_mixed_subject_refused(self):
        with self.assertRaises(CognitionError):
            EvidenceIndex((self.a,make("x",b"private",subject="other")),
                          tenant="local",subject="owner")

    def test_approved_source_required(self):
        with self.assertRaises(CognitionError):
            make("x",b"not approved",approved=False)

    def test_forged_source_bytes_refused(self):
        with self.assertRaises(CognitionError):
            EvidenceDocument(self.a.source,b"modified",(1.,0.),MODEL)

    def test_unicode_partition_exact_bytes(self):
        for span in partition(self.a,window_bytes=16,overlap_bytes=3):
            self.assertTrue(self.index.cite(span)["exact_bytes_verified"])

    def test_refuse_exact_quote_mismatch(self):
        span=partition(self.a,window_bytes=16)[0]
        with self.assertRaises(CognitionError):
            self.index.cite(span,quoted_text="invented quotation")

    def test_refuse_forged_span_digest(self):
        s=partition(self.a,window_bytes=16)[0]
        with self.assertRaises(CognitionError):
            self.index.cite(EvidenceSpan(s.source_id,s.source_sha256,s.start,s.end,"f"*64))

    def test_no_automatic_dense_fallback(self):
        with self.assertRaises(CognitionError):
            self.index.retrieve("source",mode="hybrid",query_vector=None)

    def test_explicit_hybrid(self):
        x=self.index.retrieve("source",mode="hybrid",query_vector=(1.,0.),
                              embedding_model_sha256=MODEL)
        self.assertTrue(x)
        self.assertTrue(all(not row["native_inference_executed"] for row in x))

    def test_duplicate_span_filtered(self):
        s=partition(self.a,window_bytes=16)[0]
        self.assertEqual(unique_spans((s,s)),(s,))

    def test_overlap_rerank_deterministic(self):
        s=partition(self.a,window_bytes=16,overlap_bytes=2)
        self.assertEqual(diverse_spans(((s[0],0.9),(s[1],0.8)),limit=2),
                         diverse_spans(((s[0],0.9),(s[1],0.8)),limit=2))

    def test_receipt_not_semantic_or_device_proof(self):
        s=partition(self.a,window_bytes=16)[0]
        r=self.index.attribution((s,))
        self.assertEqual(len(r["citations"]),1)
        self.assertFalse(r["semantic_entailment_proved"])
        self.assertFalse(r["model_or_device_qualified"])

    def test_reject_duplicate_source_id(self):
        with self.assertRaises(CognitionError):
            EvidenceIndex((self.a,self.a),tenant="local",subject="owner")

    def test_reject_bad_overlap(self):
        with self.assertRaises(CognitionError):
            partition(self.a,window_bytes=16,overlap_bytes=16)

    def test_reject_nan_embedding(self):
        with self.assertRaises(CognitionError):
            EvidenceDocument(self.a.source,self.a.payload,(float("nan"),0.),MODEL)

if __name__=="__main__":
    unittest.main()
