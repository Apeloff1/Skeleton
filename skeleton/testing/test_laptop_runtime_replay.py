"""Offline laptop runtime qualification: replay; test-double only, not real native E2E."""
import unittest
from skeleton.testing.laptop_runtime_test_support import FakeWorker,OUTPUT_SHA
from skeleton.ai.runtime.operational_ai.laptop_runtime.dispatcher import LaptopDispatcher
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestReplay(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker();self.api=LaptopDispatcher(self.worker)
        self.sid=self.api.dispatch("create",{})["session_id"]
    def test_real_spine_interface_is_called_once(self):
        first=self.api.dispatch("turn",{"session_id":self.sid,"request_id":"r1","prompt":"hello"})
        self.assertEqual(first["receipt"]["output_sha256"],OUTPUT_SHA)
        second=self.api.dispatch("turn",{"session_id":self.sid,"request_id":"r1","prompt":"hello"})
        self.assertTrue(second["receipt"]["replayed"])
        self.assertEqual(self.worker.generation_calls,1)
    def test_invalid_input_does_not_call_worker(self):
        for value in ("",None,42,True,"X"*32769):
            with self.subTest(value=str(value)[:20]):
                with self.assertRaises(ContractViolation):
                    self.api.dispatch("turn",{"session_id":self.sid,
                       "request_id":"r","prompt":value})
        self.assertEqual(self.worker.generation_calls,0)
    def test_replay_absence_never_generates(self):
        self.assertFalse(self.api.dispatch("replay",{"session_id":self.sid,
            "request_id":"unseen","prompt":"hello"})["found"])
        self.assertEqual(self.worker.generation_calls,0)

if __name__=="__main__":
    unittest.main()
