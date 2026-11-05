"""Executable state-machine and fail-closed regression tests."""
from skeleton.ai.runtime.operational_ai.trust_gates.control.consent import ConsentAuthority
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
import unittest
class TestConsent(unittest.TestCase):
    def test_authenticated_memory_scope(self):
        grant=ConsentAuthority(b"secret" * 8)
        token=grant.issue(tenant="t",source_id="s",operator="owner",now=1,expires=10,approved=True)
        self.assertTrue(grant.verify(token,tenant="t",source_id="s",now=2)["approved"])
        with self.assertRaises(GateViolation):grant.verify(token,tenant="other",source_id="s",now=2)
        with self.assertRaises(GateViolation):grant.verify(token,tenant="t",source_id="s",now=10)
    def test_tampered_grant_fails(self):
        authority=ConsentAuthority(b"x"*32)
        token=authority.issue(tenant="t",source_id="s",operator="o",now=1,expires=5,approved=True)
        token["mac"]="0"*64
        with self.assertRaises(GateViolation):authority.verify(token,tenant="t",source_id="s",now=2)

if __name__=="__main__":
    unittest.main()
