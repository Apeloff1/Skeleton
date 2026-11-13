"""snapshot_plan: run all source-controlled bounded policy mutations."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.casebook import run_family
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile

class SnapshotPlanSourceCases(unittest.TestCase):
    def test_two_valid_and_thirty_eight_denied(self):
        report=run_family("snapshot_plan")
        self.assertEqual(report["family"],"snapshot_plan")
        self.assertEqual(report["cases"],40)
        self.assertEqual(report["admitted"],2)
        self.assertEqual(report["rejected"],38)
        self.assertFalse(report["real_native_inference"])
        self.assertFalse(report["release_certified"])

    def test_source_profile_name(self):
        self.assertEqual(read_profile("snapshot_plan").name,"snapshot_plan")

if __name__=="__main__":
    unittest.main()
