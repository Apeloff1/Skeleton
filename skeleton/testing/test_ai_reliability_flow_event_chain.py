"""Focused operational AI reliability test: event_chain. No synthetic native E2E claim."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.event_chain import EventChain
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class EventChainTests(unittest.TestCase):
    def test_actual_sha256_linked_receipts(self):
        chain=EventChain(stream="local")
        one=chain.append("native.completed",{"sha256":"a"*64})
        two=chain.append("audit.read",{"sha256":"b"*64})
        self.assertEqual(two["previous_sha256"],one["sha256"])
        self.assertEqual(chain.verify().sequence,2)
    def test_bounded_chain_never_drops_history(self):
        chain=EventChain(stream="local",maximum=1)
        chain.append("first",{"value":1})
        with self.assertRaises(Rejected):chain.append("second",{"value":2})

if __name__=="__main__":
    unittest.main()
