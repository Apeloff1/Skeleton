"""Focused operational AI reliability test: stream_delivery. No synthetic native E2E claim."""
import unittest
from skeleton.testing.laptop_runtime_test_support import OUTPUT_SHA
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.stream_delivery import PostcommitDelivery
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class PostcommitTests(unittest.TestCase):
    def test_ordered_credits_and_receipt(self):
        stream=PostcommitDelivery({"text":"hello","output_sha256":OUTPUT_SHA,"replayed":False},
             credit=1,frame_bytes=2)
        first=stream.next()
        self.assertEqual(first["index"],0)
        with self.assertRaises(Rejected):stream.next()
        stream.acknowledge(0)
        stream.next();stream.acknowledge(1)
        stream.next();stream.acknowledge(2)
        self.assertFalse(stream.complete()["live_native_stream"])
    def test_premature_completion_fails_closed(self):
        stream=PostcommitDelivery({"text":"hello","output_sha256":OUTPUT_SHA,"replayed":False})
        with self.assertRaises(Rejected):stream.complete()

if __name__=="__main__":
    unittest.main()
