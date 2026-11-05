"""operator_escalation: exact 40-case operator policy source corpus."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.casebook import run_family
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile

class OperatorEscalationCasebookTests(unittest.TestCase):
    def test_two_admitted_and_thirty_eight_rejected(self):
        result=run_family("operator_escalation")
        self.assertEqual(result["family"],"operator_escalation")
        self.assertEqual(result["cases"],40)
        self.assertEqual(result["admitted"],2)
        self.assertEqual(result["rejected"],38)
        self.assertFalse(result["real_native_inference"])
        self.assertFalse(result["release_certified"])

    def test_family_identity(self):
        self.assertEqual(read_profile("operator_escalation").name,"operator_escalation")

if __name__=="__main__":
    unittest.main()
