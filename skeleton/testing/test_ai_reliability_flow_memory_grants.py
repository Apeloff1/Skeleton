"""Focused operational AI reliability test: memory_grants. No synthetic native E2E claim."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.memory_grants import MemoryGrants
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class MemoryGrantTests(unittest.TestCase):
    def test_consumed_hmac_grant_cannot_replay(self):
        authority=MemoryGrants(b"Z"*32)
        item=authority.issue(tenant="local",source_id="note",operator="owner",
                             now=10,expires=20,approved=True)
        self.assertTrue(authority.consume(item,tenant="local",source_id="note",now=12)["consented"])
        with self.assertRaises(GateViolation):
            authority.consume(item,tenant="local",source_id="note",now=12)
    def test_invalid_operator_or_scope_held(self):
        authority=MemoryGrants(b"Z"*32)
        with self.assertRaises(Rejected):
            authority.issue(tenant="local",source_id="note",operator="owner",
                            now=10,expires=20,approved=False)

if __name__=="__main__":
    unittest.main()
