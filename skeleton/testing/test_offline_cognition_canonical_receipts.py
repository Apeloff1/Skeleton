"""Canonical plan/citation JSON digest regression and original byte custody."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,CognitionError
from skeleton.ai.runtime.operational_ai.offline_cognition.core.planner import PlanTask,compile_plan,plan_digest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.sources import bind_source
from skeleton.ai.runtime.operational_ai.offline_cognition.core.evidence_pipeline import EvidenceDocument,EvidenceIndex,partition
from skeleton.ai.runtime.operational_ai.offline_cognition.core.orchestration import guarded_plan,plan_ready

class CanonicalReceiptTests(unittest.TestCase):
    def test_plan_digest_is_stable_on_arrays(self):
        steps=(PlanTask("source",100,0,"retrieval",()),
               PlanTask("model",200,10,"model",("source",)))
        plan=compile_plan(steps,max_tokens=100)
        self.assertEqual(len(plan["sha256"]),64)
        projection={k:plan[k] for k in ("order","edges","tokens","critical_path_ms",
                          "critical_path","source_plan_not_authority_to_execute")}
        self.assertEqual(plan_digest(projection),plan["sha256"])

    def test_plan_ready_uses_same_canonical_source_digest(self):
        scope=Scope("local","owner","a"*64,"b"*64)
        plan=guarded_plan(scope,(PlanTask("source",100,0,"retrieval",()),),
                     request_id="r",source_sha256="c"*64,
                     now_ns=1,deadline_ns=200000000,
                     token_limit=100,duration_limit_ms=1000)
        receipt=plan_ready(plan,scope,request_id="r",
                           source_sha256="c"*64,now_ns=10)
        self.assertFalse(receipt["tool_or_native_execution_authorized"])

    def test_tampered_projection_rejected_even_without_claim_change(self):
        scope=Scope("local","owner","a"*64,"b"*64)
        plan=guarded_plan(scope,(PlanTask("source",100,0,"retrieval",()),),
                     request_id="r",source_sha256="c"*64,
                     now_ns=1,deadline_ns=200000000,
                     token_limit=100,duration_limit_ms=1000)
        plan["tokens"]=99
        with self.assertRaises(CognitionError):
            plan_ready(plan,scope,request_id="r",source_sha256="c"*64,now_ns=10)

    def test_attribution_digest_handles_multiple_original_spans(self):
        raw=("Alpha ☃ source controlled bytes and citations. "*6).encode("utf-8")
        source=bind_source(raw,source_id="doc",tenant="local",subject="owner",approved=True)
        doc=EvidenceDocument(source,raw,(1.0,0.0),"a"*64)
        index=EvidenceIndex((doc,),tenant="local",subject="owner")
        spans=partition(doc,window_bytes=32,overlap_bytes=4)
        result=index.attribution(spans[:2])
        self.assertEqual(len(result["receipt_sha256"]),64)
        self.assertEqual(len(result["citations"]),2)
        self.assertFalse(result["semantic_entailment_proved"])

if __name__=="__main__":
    unittest.main()
