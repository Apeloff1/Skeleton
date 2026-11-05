"""snapshot_plan: checkpoint operator-bound functional and adversarial tests.

Test-only FakeWorker paths are never counted as real GGUF inference.
"""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.testing import exercise
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile

FAMILY="snapshot_plan"
OPERATION="checkpoint"

class SnapshotPlanCheckpointCases(unittest.TestCase):
    def test_admitted_functional_contract(self):
        self.assertTrue(exercise(FAMILY,OPERATION,attack=False))

    def test_hostile_identity_or_resource_boundary(self):
        self.assertTrue(exercise(FAMILY,OPERATION,attack=True))

    def test_profile_and_capability_are_bound(self):
        profile=read_profile(FAMILY)
        self.assertEqual(profile.name,FAMILY)
        self.assertIn(OPERATION,profile.operations)
        self.assertGreater(profile.byte_limit,0)
        self.assertGreater(profile.context_limit,0)

if __name__=="__main__":
    unittest.main()
