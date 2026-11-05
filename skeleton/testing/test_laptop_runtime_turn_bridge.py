"""Offline laptop runtime qualification: turn_bridge; test-double only, not real native E2E."""
import unittest
from skeleton.testing.laptop_runtime_test_support import FakeWorker,MODEL,TOKENIZER
from skeleton.ai.runtime.operational_ai.laptop_runtime.turn_bridge import TurnBridge
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestTurnBridge(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()
        self.sid="s_1";self.worker.spine.create(self.sid)
    def test_exactly_one_supervisor_turn_on_admission(self):
        bridge=TurnBridge(self.worker)
        response=bridge.turn(self.sid,"r_1","hello")
        self.assertEqual(response["model_sha256"],MODEL)
        self.assertEqual(self.worker.generation_calls,1)
    def test_bad_parameters_do_not_invoke_supervisor(self):
        bridge=TurnBridge(self.worker)
        for args in ({"seed":-1},{"temperature":0},
                     {"prompt":""},{"request_id":"bad/name"}):
            data={"session_id":self.sid,"request_id":"r","prompt":"hello"}
            data.update(args)
            with self.subTest(data=str(args)):
                with self.assertRaises(ContractViolation):bridge.turn(**data)
        self.assertEqual(self.worker.generation_calls,0)

if __name__=="__main__":
    unittest.main()
