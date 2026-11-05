"""Focused runtime reliability flow checks; not real GGUF inference evidence."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.event_chain import EventChain
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class HashChainTests(unittest.TestCase):
    def test_event_sha_links_to_exact_predecessor(self):
        journal=EventChain(stream="laptop")
        a=journal.append("native.completed",{"digest":"a"*64})
        b=journal.append("audit.read",{"digest":"b"*64})
        self.assertEqual(b["previous_sha256"],a["sha256"])
        self.assertEqual(journal.verify().sequence,2)
    def test_history_never_discarded_to_admit_new_event(self):
        journal=EventChain(stream="laptop",maximum=1)
        journal.append("test",{"x":1})
        with self.assertRaises(Rejected):journal.append("test",{"x":2})
if __name__=="__main__":unittest.main()
