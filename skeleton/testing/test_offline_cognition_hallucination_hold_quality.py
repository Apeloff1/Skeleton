"""hallucination_hold: finite empirical quality and reviewer holds."""
import unittest
import json
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,CognitionError
from skeleton.ai.runtime.operational_ai.offline_cognition.families.hallucination_hold import quality
S=Scope("local","owner","a"*64,"b"*64)

class HallucinationHoldQualityTests(unittest.TestCase):
    def setUp(self):
        self.binding=quality.BenchmarkBinding(S,"fixture","1"*64,"2"*64,"3"*64,"4"*64,"5"*64,1000,True)

    def test_bounded_independent_benchmark_claim(self):
        from skeleton.ai.runtime.operational_ai.offline_cognition.core.evaluation import EvaluationCase
        cases=(EvaluationCase("case1","b"*64,"c"*64,"c"*64,True),)
        result=quality.evaluate(self.binding,cases,min_cases=1,min_lower_bound=0)
        self.assertEqual(result["passed"],1)
        self.assertFalse(result["native_gguf_qualified"])

    def test_original_latency_sample_quantiles(self):
        rows=(quality.LatencySample("sample",50,10,10,True),)
        result=quality.latencies(rows,min_samples=1)
        self.assertEqual(result["latency_ms_p95"],50)
        self.assertFalse(result["p99_evidence_sufficient"])

    def test_closed_model_output_shape(self):
        raw=json.dumps({"schema":"reply","answer":"text","citations":[],"refusal":False}).encode()
        result=quality.response(raw,schema="reply")
        self.assertFalse(result["model_generated_content_is_policy"])

    def test_unknown_authority_rejected(self):
        raw=json.dumps({"schema":"reply","answer":"text","citations":[],"refusal":False,"admin":True}).encode()
        with self.assertRaises(CognitionError):
            quality.response(raw,schema="reply")

    def test_no_self_promotion(self):
        self.assertFalse(quality.assurance()["model_auto_promotion"])

if __name__=="__main__":
    unittest.main()
