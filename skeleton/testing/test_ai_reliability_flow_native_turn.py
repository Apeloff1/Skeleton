"""Focused operational AI reliability test: native_turn. No synthetic native E2E claim."""
import unittest
from skeleton.testing.reliability_fabric_test_support import scenario,FakeWorker
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.preflight import REQUIRED_INFERENCE
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.native_turn import complete,replay_only
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class NativeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()
        self.worker.spine.create("session")
        self.records={x:scenario(x,subject="owner") for x in REQUIRED_INFERENCE}
    def test_single_spine_turn_and_authoritative_replay(self):
        output=complete(self.worker,self.records,session_id="session",request_id="r1",prompt="hello")
        self.assertEqual(output["receipt"]["text"],"hello")
        self.assertFalse(output["assurance"].live_native_proven_by_fixture)
        self.assertEqual(self.worker.generation_calls,1)
        again=replay_only(self.worker,session_id="session",request_id="r1",prompt="hello")
        self.assertTrue(again["found"])
        self.assertFalse(again["generated"])
        self.assertEqual(self.worker.generation_calls,1)
    def test_rejected_preflight_never_invokes_backend(self):
        self.records["lease_epoch"]["details"]["live"]=False
        with self.assertRaises(Rejected):
            complete(self.worker,self.records,session_id="session",request_id="r2",prompt="hello")
        self.assertEqual(self.worker.generation_calls,0)

if __name__=="__main__":
    unittest.main()
