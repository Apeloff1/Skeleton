"""Focused runtime reliability flow checks; not real GGUF inference evidence."""
import unittest
from skeleton.testing.laptop_runtime_test_support import OUTPUT_SHA
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.stream_delivery import PostcommitDelivery
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class DeliveryCases(unittest.TestCase):
    def test_postcommit_output_requires_ordered_ack(self):
        item=PostcommitDelivery({"text":"hello","output_sha256":OUTPUT_SHA,"replayed":False},
                                credit=1,frame_bytes=2)
        self.assertEqual(item.next()["index"],0)
        with self.assertRaises(Rejected):item.next()
        item.acknowledge(0)
        for n in (1,2):
            self.assertEqual(item.next()["index"],n)
            item.acknowledge(n)
        receipt=item.complete()
        self.assertFalse(receipt["live_native_stream"])
        self.assertEqual(receipt["frame_count"],3)
    def test_unacknowledged_output_cannot_be_completed(self):
        item=PostcommitDelivery({"text":"hello","output_sha256":OUTPUT_SHA,"replayed":False})
        item.next()
        with self.assertRaises(Rejected):item.complete()
if __name__=="__main__":unittest.main()
