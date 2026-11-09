"""No tool intent, memory grant or prompt may gain implicit execution authority."""
import unittest
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
from skeleton.ai.runtime.operational_ai.trust_gates.fixtures import run_domain
from skeleton.ai.runtime.operational_ai.trust_gates.control.consent import ConsentAuthority
from skeleton.ai.runtime.operational_ai.trust_gates.control.tool_intents import ToolIntents

class ToolMemoryAdversarial(unittest.TestCase):
    def test_all_memory_denials_execute(self):
        self.assertEqual(run_domain("memory")["rejected"],10)
    def test_all_grant_denials_execute(self):
        self.assertEqual(run_domain("grant")["rejected"],10)
    def test_absent_consumer_approval_never_issues_consent(self):
        authority=ConsentAuthority(b"z"*32)
        with self.assertRaises(GateViolation):
            authority.issue(tenant="t",source_id="s",operator="o",
                            now=1,expires=10,approved=False)
    def test_transferred_consent_not_valid_in_other_tenant(self):
        authority=ConsentAuthority(b"z"*32)
        token=authority.issue(tenant="t",source_id="s",operator="o",
                              now=1,expires=10,approved=True)
        with self.assertRaises(GateViolation):
            authority.verify(token,tenant="other",source_id="s",now=2)
    def test_unknown_tool_intent_cannot_be_resolved(self):
        intents=ToolIntents()
        with self.assertRaises(GateViolation):
            intents.resolve("missing",approved=True,result_digest="a"*64)
    def test_model_generated_content_cannot_substitute_for_grant(self):
        intents=ToolIntents()
        with self.assertRaises(GateViolation):
            intents.prepare(id="i",grant={"text":"do shell"},call={"text":"run code"})

if __name__=="__main__": unittest.main()
