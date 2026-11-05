"""Offline laptop runtime qualification: startup; test-double only, not real native E2E."""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch
from skeleton.testing.laptop_runtime_test_support import FakeWorker
from skeleton.ai.runtime.operational_ai.laptop_runtime.startup import activate_checked
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestStartup(unittest.TestCase):
    def report(self,**overrides):
        values={"model_sha256":"a"*64,"content_verified":True,
                "rights_approved":True,"archive_sha256":"b"*64,"source_sha":"c"*40}
        values.update(overrides);return SimpleNamespace(**values)
    def test_missing_approved_installation_never_activates_native(self):
        with patch("skeleton.ai.runtime.operational_ai.deployment.install.doctor.inspect_installed_model",
             return_value=self.report(rights_approved=False)) as doctor:
            with patch("skeleton.ai.runtime.operational_ai.deployment.production.startup.activate") as activation:
                with self.assertRaises(ContractViolation):
                    activate_checked(model_root="/model",state_dir="/state",
                        tenant="local",subject="owner",capacity_root="/capacity")
                doctor.assert_called_once();activation.assert_not_called()
    def test_source_receipt_precedes_real_activation(self):
        ordered=[]
        def inspect(_):
            ordered.append("verified-source");return self.report()
        def activate(**kwargs):
            ordered.append("activate-real-runtime");return ExitStack(),FakeWorker()
        with patch("skeleton.ai.runtime.operational_ai.deployment.install.doctor.inspect_installed_model",side_effect=inspect):
            with patch("skeleton.ai.runtime.operational_ai.deployment.production.startup.activate",side_effect=activate):
                stack,worker,source=activate_checked(model_root="/model",state_dir="/state",
                    tenant="local",subject="owner",capacity_root="/capacity")
        self.assertEqual(ordered,["verified-source","activate-real-runtime"])
        self.assertTrue(source.rights_approved)
        stack.close()
    def test_nonisolated_backend_not_allowed(self):
        with self.assertRaises(ContractViolation):
            activate_checked(model_root="/model",state_dir="/state",
                tenant="local",subject="owner",isolated=False)

if __name__=="__main__":
    unittest.main()
