"""burst_control/fusion: original core and adversarial boundary cases."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.testing import exercise
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile
FAMILY="burst_control"
OPERATION="fusion"

class BurstControlFusionTests(unittest.TestCase):
    def test_bounded_source_operation(self):
        self.assertTrue(exercise(FAMILY,OPERATION,attack=False))

    def test_hostile_principal_and_capacity(self):
        self.assertTrue(exercise(FAMILY,OPERATION,attack=True))

    def test_exact_operator_profile(self):
        profile=read_profile(FAMILY)
        self.assertEqual(profile.name,FAMILY)
        self.assertIn(OPERATION,profile.operations)
        self.assertGreater(profile.context_limit,0)
        self.assertGreater(profile.byte_limit,0)

if __name__=="__main__":
    unittest.main()
