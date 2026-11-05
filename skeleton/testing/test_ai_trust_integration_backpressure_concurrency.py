"""Streaming credit boundaries under concurrent publishers and acknowledgers."""
import concurrent.futures
import unittest
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
from skeleton.ai.runtime.operational_ai.trust_gates.control.backpressure import BackpressureWindow

class ConcurrentBackpressure(unittest.TestCase):
    def test_single_credit_is_never_spent_twice(self):
        stream=BackpressureWindow(window=1,max_frames=8)
        def emit(text):
            try:
                return ("ok",stream.publish(text)["index"])
            except GateViolation:
                return ("blocked",None)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            replies=list(pool.map(emit,["left","right"]))
        self.assertCountEqual([x[0] for x in replies],["ok","blocked"])
        self.assertEqual(stream.acknowledge(0),0)
        self.assertEqual(stream.complete()["frames"],1)
    def test_acknowledge_future_frame_is_forbidden(self):
        stream=BackpressureWindow(window=2)
        stream.publish("first")
        with self.assertRaises(GateViolation):stream.acknowledge(1)
        stream.acknowledge(0)
        with self.assertRaises(GateViolation):stream.acknowledge(0)
    def test_cancel_quarantines_unacknowledged_output(self):
        stream=BackpressureWindow(window=3)
        for text in ("a","b","c"):stream.publish(text)
        self.assertEqual(stream.cancel()["dropped_unacknowledged_frames"],3)
        with self.assertRaises(GateViolation):stream.complete()

if __name__=="__main__": unittest.main()
