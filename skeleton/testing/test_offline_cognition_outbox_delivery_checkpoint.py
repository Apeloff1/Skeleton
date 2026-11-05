"""outbox_delivery: checkpoint bounded and hostile source boundaries."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.testing import exercise
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile
FAMILY="outbox_delivery"
OPERATION="checkpoint"

class OutboxDeliveryCheckpointTests(unittest.TestCase):
    def test_finite_real_contract(self):
        self.assertTrue(exercise(FAMILY,OPERATION,attack=False))

    def test_hostile_identity_resource_contract(self):
        self.assertTrue(exercise(FAMILY,OPERATION,attack=True))

    def test_registered_profile_scope(self):
        profile=read_profile(FAMILY)
        self.assertEqual(profile.name,FAMILY)
        self.assertIn(OPERATION,profile.operations)
        self.assertGreater(profile.byte_limit,0)
        self.assertGreater(profile.context_limit,0)

if __name__=="__main__":
    unittest.main()
