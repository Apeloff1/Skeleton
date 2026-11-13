"""Offline laptop runtime qualification: once_guard; test-double only, not real native E2E."""
import unittest
from skeleton.ai.runtime.operational_ai.laptop_runtime.once_guard import OnceGuard
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestOnceGuard(unittest.TestCase):
    def test_same_request_cannot_overlap(self):
        guard=OnceGuard(maximum=1)
        with guard.hold("t","s","r"):
            with self.assertRaises(ContractViolation):
                with guard.hold("t","s","r"):pass
            with self.assertRaises(ContractViolation):
                with guard.hold("t","s","other"):pass
        with guard.hold("t","s","r"):
            self.assertEqual(guard.snapshot()["pending"],1)
        self.assertEqual(guard.snapshot()["pending"],0)
    def test_invalid_identity_precedes_lease(self):
        guard=OnceGuard()
        with self.assertRaises(ContractViolation):
            with guard.hold("t","/invalid","r"):pass

if __name__=="__main__":
    unittest.main()
