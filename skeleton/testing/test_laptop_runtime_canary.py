"""Offline laptop runtime qualification: canary; test-double only, not real native E2E."""
import unittest
from unittest.mock import patch
from skeleton.testing.laptop_runtime_test_support import FakeWorker
from skeleton.ai.runtime.operational_ai.laptop_runtime.canary import run_native_canary
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestNativeCanary(unittest.TestCase):
    def test_model_never_called_without_operator_approval(self):
        with patch("skeleton.ai.runtime.operational_ai.orchestration.execution_spine.qualification.run_canary") as native:
            with self.assertRaises(ContractViolation):
                run_native_canary(FakeWorker(),approve=False)
            native.assert_not_called()
    def test_response_cannot_pretend_release_qualified(self):
        with patch("skeleton.ai.runtime.operational_ai.orchestration.execution_spine.qualification.run_canary",
                   return_value={"status":"fake-success"}) as native:
            with self.assertRaises(ContractViolation):
                run_native_canary(FakeWorker(),approve=True)
            native.assert_called_once()

if __name__=="__main__":
    unittest.main()
