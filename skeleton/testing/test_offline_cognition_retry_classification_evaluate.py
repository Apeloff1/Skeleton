"""retry_classification: evaluate operation with real bounded and hostile cases."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.testing import exercise
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile
NAME="retry_classification"
OP="evaluate"

class RetryClassificationEvaluateTests(unittest.TestCase):
    def test_bounded_functional_path(self):
        self.assertTrue(exercise(NAME,OP,attack=False))

    def test_hostile_adversarial_path(self):
        self.assertTrue(exercise(NAME,OP,attack=True))

    def test_canonical_profile_and_operation(self):
        profile=read_profile(NAME)
        self.assertEqual(profile.name,NAME)
        self.assertIn(OP,profile.operations)
        self.assertGreater(profile.context_limit,0)
        self.assertGreater(profile.byte_limit,0)

if __name__=="__main__":
    unittest.main()
