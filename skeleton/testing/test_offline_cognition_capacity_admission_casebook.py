"""capacity_admission: source-controlled positive and adversarial policies."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.casebook import run_family
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile

class CapacityAdmissionCasebookTests(unittest.TestCase):
    def test_all_forty_policy_mutations(self):
        r=run_family("capacity_admission")
        self.assertEqual(r["family"],"capacity_admission")
        self.assertEqual(r["cases"],40)
        self.assertEqual(r["admitted"],2)
        self.assertEqual(r["rejected"],38)
        self.assertFalse(r["real_native_inference"])
        self.assertFalse(r["release_certified"])

    def test_profile_identity(self):
        self.assertEqual(read_profile("capacity_admission").name,"capacity_admission")

if __name__=="__main__":
    unittest.main()
