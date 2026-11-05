"""Orchestration hardening: no swapped tool source or mutated DAG projection."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,CognitionError
from skeleton.ai.runtime.operational_ai.offline_cognition.core.sources import bind_source
from skeleton.ai.runtime.operational_ai.offline_cognition.core.planner import PlanTask
from skeleton.ai.runtime.operational_ai.offline_cognition.core.orchestration import (
    ReadResult,propose_read,guarded_plan,plan_ready,
)

class OrchestrationHardeningTests(unittest.TestCase):
    def test_intent_source_id_cannot_be_swapped(self):
        scope=Scope("local","owner","a"*64,"b"*64)
        raw=b"Original source bytes"
        source=bind_source(raw,source_id="different",tenant="local",subject="owner",approved=True)
        intent=propose_read(scope,request_id="r",source_id="original",expires_ns=100)
        with self.assertRaises(CognitionError):
            ReadResult(intent,source,scope,"r",raw,50)

    def test_intent_source_limit_cannot_be_swapped(self):
        scope=Scope("local","owner","a"*64,"b"*64)
        raw=b"Original source bytes"
        source=bind_source(raw,source_id="original",tenant="local",subject="owner",approved=True)
        intent=propose_read(scope,request_id="r",source_id="original",expires_ns=100,limit=2)
        with self.assertRaises(CognitionError):
            ReadResult(intent,source,scope,"r",raw,50,limit=10)

    def test_compiled_plan_projection_cannot_be_swapped(self):
        scope=Scope("local","owner","a"*64,"b"*64)
        p=guarded_plan(scope,(PlanTask("read",100,0,"retrieval",()),
             PlanTask("run",200,20,"model",("read",))),request_id="r",
             source_sha256="c"*64,now_ns=1,deadline_ns=1000000000,
             token_limit=1000,duration_limit_ms=1000)
        p["order"]=("run","read")
        with self.assertRaises(CognitionError):
            plan_ready(p,scope,request_id="r",source_sha256="c"*64,now_ns=50)

if __name__=="__main__":
    unittest.main()
