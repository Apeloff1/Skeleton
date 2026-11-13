"""Executable state-machine and fail-closed regression tests."""
from skeleton.ai.runtime.operational_ai.trust_gates.control.tool_intents import ToolIntents
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
import unittest
class TestToolIntents(unittest.TestCase):
    def test_prepared_and_resolved_caller_read_intent(self):
        intents=ToolIntents()
        grant={"actor_id":"owner","tool_id":"read_text","expires_at":20,"now":10,
               "nonce":"n1","rights":["read"],"scope":"owner:read_text"}
        call={"grant_id":"n1","tool_id":"read_text",
              "args":{"path":"docs/readme.md","byte_limit":4096},
              "risk":"low","approved":True,"request_id":"r1"}
        self.assertEqual(intents.prepare(id="i1",grant=grant,call=call)["state"],"prepared")
        with self.assertRaises(GateViolation):intents.resolve("i1")
        self.assertEqual(intents.resolve("i1",approved=True,result_digest="a"*64)["state"],"resolved")
        with self.assertRaises(GateViolation):intents.abort("i1")
    def test_grant_cannot_authorize_shell(self):
        intents=ToolIntents()
        grant={"actor_id":"owner","tool_id":"shell","expires_at":20,"now":10,
               "nonce":"n1","rights":["read"],"scope":"owner:shell"}
        call={"grant_id":"n1","tool_id":"shell",
              "args":{"path":"docs/readme.md","byte_limit":4096},
              "risk":"low","approved":True,"request_id":"r1"}
        with self.assertRaises(GateViolation):intents.prepare(id="x",grant=grant,call=call)

if __name__=="__main__":
    unittest.main()
