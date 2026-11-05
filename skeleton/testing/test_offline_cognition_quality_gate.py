"""Offline evaluation strict envelopes, finite tails and provenance-based holds."""
import unittest
import json
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,CognitionError,hash_bytes
from skeleton.ai.runtime.operational_ai.offline_cognition.core.quality_gate import (
    BenchmarkBinding,evaluate_exact,LatencySample,distribution,inspect_envelope,
    verify_reply_evidence,refusal_statistics,guarded_review,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.core.evidence_pipeline import (
    EvidenceDocument,EvidenceIndex,partition,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.core.sources import bind_source
from skeleton.ai.runtime.operational_ai.offline_cognition.core.receipts import NativeReceipt
from skeleton.ai.runtime.operational_ai.offline_cognition.core.evaluation import EvaluationCase
S=Scope("local","owner","a"*64,"b"*64)

def benchmark():
    return BenchmarkBinding(S,"offline_eval","1"*64,"2"*64,"3"*64,
                            "4"*64,"5"*64,1000,True)

class QualityGateTests(unittest.TestCase):
    def test_benchmark_requires_finite_identity(self):
        self.assertEqual(len(benchmark().digest()),64)

    def test_exact_digest_evaluation_does_not_claim_real_model(self):
        cases=(EvaluationCase("a","1"*64,"2"*64,"2"*64,True),
               EvaluationCase("b","3"*64,"4"*64,"5"*64,True))
        report=evaluate_exact(benchmark(),cases,min_cases=2,min_lower_bound=0)
        self.assertEqual(report["passed"],1)
        self.assertFalse(report["native_gguf_qualified"])

    def test_latencies_have_empirical_tail(self):
        rows=tuple(LatencySample("task"+str(i),i+1,1,10,True) for i in range(100))
        report=distribution(rows,min_samples=100)
        self.assertEqual(report["latency_ms_p99"],99)
        self.assertTrue(report["p99_evidence_sufficient"])

    def test_refuse_duplicate_latency_identity(self):
        rows=(LatencySample("same",1,1,1,True),)*2
        with self.assertRaises(CognitionError):
            distribution(rows)

    def test_reject_duplicate_json_keys(self):
        with self.assertRaises(CognitionError):
            inspect_envelope(b'{"schema":"x","schema":"x","answer":"hi","citations":[],"refusal":false}',expected_schema="x")

    def test_valid_closed_response_shape_does_not_grant_authority(self):
        raw=json.dumps({"schema":"offline_reply","answer":"Text","citations":[],
                        "refusal":False}).encode()
        report=inspect_envelope(raw,expected_schema="offline_reply")
        self.assertFalse(report["model_generated_content_is_policy"])

    def test_refuse_unknown_envelope_privilege(self):
        raw=json.dumps({"schema":"offline_reply","answer":"Text","citations":[],
                        "refusal":False,"admin":True}).encode()
        with self.assertRaises(CognitionError):
            inspect_envelope(raw,expected_schema="offline_reply")

    def test_grounding_requires_source_receipts(self):
        text="Original offline document"
        raw=text.encode()
        src=bind_source(raw,source_id="doc",tenant="local",subject="owner",approved=True)
        index=EvidenceIndex((EvidenceDocument(src,raw),),tenant="local",subject="owner")
        r=NativeReceipt(S,"session","r",text,hash_bytes(raw),5,6,False)
        span=partition(index.documents["doc"],window_bytes=64)[0]
        proof=verify_reply_evidence(r,index,(span,),grounding_required=True)
        self.assertTrue(proof["byte_provenance_verified"])
        self.assertFalse(proof["semantic_entailment_proved"])
        self.assertFalse(proof["automatic_publication_authorized"])

    def test_grounding_missing_citation_is_refused(self):
        raw=b"Original offline document"
        src=bind_source(raw,source_id="doc",tenant="local",subject="owner",approved=True)
        index=EvidenceIndex((EvidenceDocument(src,raw),),tenant="local",subject="owner")
        r=NativeReceipt(S,"session","r","Text",hash_bytes(b"Text"),5,6,False)
        with self.assertRaises(CognitionError):
            verify_reply_evidence(r,index,(),grounding_required=True)

    def test_refusal_classification_is_not_automated_promotion(self):
        report=refusal_statistics(((True,True),(False,False),(False,True)))
        self.assertFalse(report["automatic_promotion"])

    def test_even_perfect_source_proof_keeps_release_hold(self):
        b=benchmark()
        metric={"binding_sha256":b.digest(),"wilson_lower":1.0,"sample_floor_met":True}
        lat={"sample_floor_met":True,"p99_evidence_sufficient":True}
        ground={"byte_provenance_verified":True,"semantic_entailment_proved":False}
        result=guarded_review(b,metric,lat,ground)
        self.assertEqual(result["state"],"review-held")
        self.assertFalse(result["release_accepted"])

    def test_refuse_false_semantic_attestation(self):
        b=benchmark()
        with self.assertRaises(CognitionError):
            guarded_review(b,{"binding_sha256":b.digest()},{"sample_floor_met":False},
                           {"semantic_entailment_proved":True})

if __name__=="__main__":
    unittest.main()
