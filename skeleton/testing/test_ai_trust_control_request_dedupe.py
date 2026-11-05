"""Executable state-machine and fail-closed regression tests."""
from skeleton.ai.runtime.operational_ai.trust_gates.control.request_dedupe import RequestDedupe
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
import unittest
class TestRequestDedupe(unittest.TestCase):
    def test_replay_cannot_run_twice(self):
        table=RequestDedupe()
        self.assertEqual(table.begin("tenant","req","digest"),("new",None))
        with self.assertRaises(GateViolation):table.begin("tenant","req","digest")
        table.commit("tenant","req","digest",{"revision":1})
        self.assertEqual(table.begin("tenant","req","digest"),("replay",{"revision":1}))
        with self.assertRaises(GateViolation):table.begin("tenant","req","other")
    def test_abort_releases_only_pending_intent(self):
        table=RequestDedupe(maximum=1)
        table.begin("t","a","sig")
        table.abort("t","a","sig")
        self.assertEqual(table.begin("t","b","sig"),("new",None))
        with self.assertRaises(GateViolation):table.abort("t","a","sig")

if __name__=="__main__":
    unittest.main()
