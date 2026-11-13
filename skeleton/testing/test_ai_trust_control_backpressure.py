"""Executable state-machine and fail-closed regression tests."""
from skeleton.ai.runtime.operational_ai.trust_gates.control.backpressure import BackpressureWindow
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
import unittest
class TestBackpressure(unittest.TestCase):
    def test_receiver_ack_controls_credits(self):
        stream=BackpressureWindow(window=1,max_bytes=8)
        stream.publish("A")
        with self.assertRaises(GateViolation):stream.publish("B")
        stream.acknowledge(0)
        stream.publish("B")
        stream.acknowledge(1)
        self.assertEqual(stream.complete()["frames"],2)
    def test_cancel_fences_further_output(self):
        stream=BackpressureWindow(window=2)
        stream.publish("A")
        self.assertEqual(stream.cancel()["dropped_unacknowledged_frames"],1)
        with self.assertRaises(GateViolation):stream.publish("B")

if __name__=="__main__":
    unittest.main()
