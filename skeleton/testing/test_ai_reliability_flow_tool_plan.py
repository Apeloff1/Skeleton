"""Focused operational AI reliability test: tool_plan. No synthetic native E2E claim."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.tool_plan import ToolPlan
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
class ToolPlanTests(unittest.TestCase):
    def test_exact_read_only_intent_and_signed_resolution(self):
        grant={"actor_id":"owner","tool_id":"read_text","expires_at":20,
             "now":10,"nonce":"grant1","rights":["read"],"scope":"owner:read_text"}
        call={"grant_id":"grant1","tool_id":"read_text",
             "args":{"path":"docs/readme.md","byte_limit":1024},
             "risk":"low","approved":True,"request_id":"req"}
        plan=ToolPlan()
        self.assertEqual(plan.prepare(request_id="req",intent_id="i1",
                     grant=grant,call=call).state,"prepared")
        self.assertEqual(plan.settle(request_id="req",intent_id="i1",
                     result_sha256="a"*64,approved=True).state,"resolved")
    def test_mismatched_parent_request_rejected(self):
        with self.assertRaises(Rejected):
            ToolPlan().prepare(request_id="req",intent_id="i1",grant={},
                               call={"request_id":"other"})

if __name__=="__main__":
    unittest.main()
