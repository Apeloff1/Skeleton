"""Focused runtime reliability flow checks; not real GGUF inference evidence."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.memory_grants import MemoryGrants
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class MemoryGrantTests(unittest.TestCase):
    def test_strong_one_use_scoped_hmac(self):
        authority=MemoryGrants(b"K"*32)
        grant=authority.issue(tenant="local",source_id="note",operator="owner",
                              now=10,expires=20,approved=True)
        self.assertTrue(authority.consume(grant,tenant="local",source_id="note",now=12)["consented"])
        with self.assertRaises(GateViolation):
            authority.consume(grant,tenant="local",source_id="note",now=12)
    def test_missing_operator_approval_refused(self):
        with self.assertRaises(Rejected):
            MemoryGrants(b"K"*32).issue(tenant="local",source_id="note",
                    operator="owner",now=10,expires=20,approved=False)
if __name__=="__main__":unittest.main()
