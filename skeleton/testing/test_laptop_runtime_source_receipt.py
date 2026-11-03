"""Offline laptop runtime qualification: source_receipt; test-double only, not real native E2E."""
import unittest
from unittest.mock import patch,MagicMock
from types import SimpleNamespace
from skeleton.ai.runtime.operational_ai.laptop_runtime.installation import source_receipt
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestSourceReceipt(unittest.TestCase):
    def report(self,**changes):
        data={"model_sha256":"a"*64,"archive_sha256":"b"*64,
              "source_sha":"c"*40,"content_verified":True,
              "rights_approved":True}
        data.update(changes);return SimpleNamespace(**data)
    @patch("skeleton.ai.runtime.operational_ai.deployment.install.doctor.inspect_installed_model")
    def test_actual_installer_receipt_required(self,doctor):
        doctor.return_value=self.report()
        result=source_receipt("/already-installed",expected_model_sha256="a"*64)
        self.assertTrue(result.content_verified)
        doctor.assert_called_once()
    @patch("skeleton.ai.runtime.operational_ai.deployment.install.doctor.inspect_installed_model")
    def test_unapproved_rights_and_mismatched_model_hold(self,doctor):
        doctor.return_value=self.report(rights_approved=False)
        with self.assertRaises(ContractViolation):source_receipt("/already-installed")
        doctor.return_value=self.report()
        with self.assertRaises(ContractViolation):
            source_receipt("/already-installed",expected_model_sha256="d"*64)

if __name__=="__main__":
    unittest.main()
