"""review_ready/checkpoint: real finite operation and adversarial boundary tests."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.testing import exercise
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile
FAMILY="review_ready"
OP="checkpoint"

class ReviewReadyCheckpointTests(unittest.TestCase):
    def test_bounded_real_contract(self):
        self.assertTrue(exercise(FAMILY,OP,attack=False))

    def test_adversarial_operator_scope(self):
        self.assertTrue(exercise(FAMILY,OP,attack=True))

    def test_exact_source_profile(self):
        profile=read_profile(FAMILY)
        self.assertEqual(profile.name,FAMILY)
        self.assertIn(OP,profile.operations)
        self.assertGreater(profile.byte_limit,0)
        self.assertGreater(profile.context_limit,0)

if __name__=="__main__":
    unittest.main()
