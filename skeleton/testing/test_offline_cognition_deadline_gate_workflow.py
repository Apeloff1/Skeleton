"""deadline_gate: real deterministic planning and strict effects fence tests."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,CognitionError
from skeleton.ai.runtime.operational_ai.offline_cognition.core.planner import PlanTask
from skeleton.ai.runtime.operational_ai.offline_cognition.core.orchestration import CircuitSnapshot
from skeleton.ai.runtime.operational_ai.offline_cognition.families.deadline_gate import workflow
S=Scope("local","owner","a"*64,"b"*64)
D="c"*64

class DeadlineGateWorkflowTests(unittest.TestCase):
    def task(self):
        return (PlanTask("source",100,0,"retrieval",()),
                PlanTask("generate",500,100,"model",("source",)))

    def test_plan_is_inert(self):
        result=workflow.compile(S,self.task(),request_id="r",source_sha256=D,
            now_ns=1,deadline_ns=1000000000,token_limit=1000,duration_limit_ms=1000)
        self.assertEqual(result["critical_path_ms"],600)
        self.assertFalse(result["approved_to_execute"])

    def test_deadline_is_fail_closed(self):
        with self.assertRaises(CognitionError):
            workflow.compile(S,self.task(),request_id="r",source_sha256=D,
                now_ns=1,deadline_ns=100,token_limit=1000,duration_limit_ms=1000)

    def test_tool_intent_cannot_execute(self):
        intent=workflow.read_only_proposal(S,request_id="r",source_id="doc",expires_ns=100)
        self.assertEqual(intent.scope_sha256,S.digest())

    def test_unknown_native_effect_has_no_retry(self):
        outcome=workflow.outcome("native-effect-unknown",dispatch_marker=True,
                                 authoritative_commit=False)
        self.assertFalse(outcome["automatic_retry_allowed"])

    def test_circuit_recovery_is_only_a_held_request(self):
        old=CircuitSnapshot(S.digest(),2,3,100,True)
        result=workflow.recovery_request(old,S,expected_revision=2,operator_approved=True)
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["operator_signature_verified"])

if __name__=="__main__":
    unittest.main()
