"""preemption_hold: source-controlled positive and adversarial policies."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.casebook import run_family
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile

class PreemptionHoldCasebookTests(unittest.TestCase):
    def test_all_forty_policy_mutations(self):
        r=run_family("preemption_hold")
        self.assertEqual(r["family"],"preemption_hold")
        self.assertEqual(r["cases"],40)
        self.assertEqual(r["admitted"],2)
        self.assertEqual(r["rejected"],38)
        self.assertFalse(r["real_native_inference"])
        self.assertFalse(r["release_certified"])

    def test_profile_identity(self):
        self.assertEqual(read_profile("preemption_hold").name,"preemption_hold")

if __name__=="__main__":
    unittest.main()
