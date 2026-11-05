"""Offline laptop runtime qualification: dispatcher; test-double only, not real native E2E."""
import unittest
from skeleton.testing.laptop_runtime_test_support import FakeWorker,MODEL,TOKENIZER
from skeleton.ai.runtime.operational_ai.laptop_runtime.dispatcher import LaptopDispatcher
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestDispatcher(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker();self.api=LaptopDispatcher(self.worker)
    def test_create_turn_replay_history_and_close(self):
        sid=self.api.dispatch("create",{})["session_id"]
        first=self.api.dispatch("turn",{"session_id":sid,"request_id":"req1","prompt":"hello"})
        self.assertEqual(first["receipt"]["model_sha256"],MODEL)
        self.assertEqual(self.worker.generation_calls,1)
        replay=self.api.dispatch("replay",{"session_id":sid,"request_id":"req1","prompt":"hello"})
        self.assertTrue(replay["found"])
        self.assertTrue(replay["replay"]["replayed"])
        self.assertEqual(self.worker.generation_calls,1)
        self.assertEqual(len(self.api.dispatch("history",{"session_id":sid})["messages"]),1)
        self.assertTrue(self.api.dispatch("close",{"session_id":sid})["closed"])
    def test_unsupported_system_prompt_is_not_ignored(self):
        with self.assertRaises(ContractViolation):
            self.api.dispatch("create",{"system":"unapproved override"})
    def test_unknown_operation_does_not_generate(self):
        with self.assertRaises(ContractViolation):
            self.api.dispatch("tools",{"command":"rm -rf /"})
        self.assertEqual(self.worker.generation_calls,0)
    def test_status_and_doctor_do_not_generate(self):
        self.assertFalse(self.api.dispatch("doctor",{})["release_certified"])
        self.assertEqual(self.api.dispatch("identity",{})["identity"]["model_sha256"],MODEL)
        self.assertIn("status",self.api.dispatch("status",{}))
        self.assertEqual(self.worker.generation_calls,0)

if __name__=="__main__":
    unittest.main()
