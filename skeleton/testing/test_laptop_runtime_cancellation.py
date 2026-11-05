"""Offline laptop runtime qualification: cancellation; test-double only, not real native E2E."""
import unittest
from skeleton.ai.runtime.operational_ai.laptop_runtime.cancel_registry import CancellationRegistry
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestCancellation(unittest.TestCase):
    def test_live_cooperative_signal_is_not_native_kill_evidence(self):
        registry=CancellationRegistry(maximum=1)
        item=registry.register("session","request",deadline_ms=1000)
        receipt=registry.cancel("session","request")
        self.assertTrue(receipt["cooperative_cancel_requested"])
        self.assertFalse(receipt["native_process_terminated_proved"])
        registry.retire("session","request",item)
    def test_duplicate_active_cancel_handle_fails_closed(self):
        registry=CancellationRegistry(maximum=1)
        item=registry.register("s","r",deadline_ms=1000)
        with self.assertRaises(ContractViolation):
            registry.register("s","r",deadline_ms=1000)
        with self.assertRaises(ContractViolation):
            registry.register("s","other",deadline_ms=1000)
        registry.retire("s","r",item)

if __name__=="__main__":
    unittest.main()
