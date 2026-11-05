"""chunk_partition/fusion: standard bounded operation and hostile boundary tests."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.testing import exercise
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile
FAMILY="chunk_partition"
OPERATION="fusion"

class ChunkPartitionFusionTests(unittest.TestCase):
    def test_real_bounded_operator_contract(self):
        self.assertTrue(exercise(FAMILY,OPERATION,attack=False))

    def test_adversarial_scope_and_resources(self):
        self.assertTrue(exercise(FAMILY,OPERATION,attack=True))

    def test_profile_identity_and_capability(self):
        p=read_profile(FAMILY)
        self.assertEqual(p.name,FAMILY)
        self.assertIn(OPERATION,p.operations)
        self.assertGreater(p.context_limit,0)
        self.assertGreater(p.byte_limit,0)

if __name__=="__main__":
    unittest.main()
