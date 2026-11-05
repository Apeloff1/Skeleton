"""Complete source and adversarial-fixture custody checks."""
import unittest
from skeleton.ai.runtime.operational_ai.laptop_runtime.inventory import inspect
class TestLaptopInventory(unittest.TestCase):
    def test_every_adversarial_source_case_is_present(self):
        result=inspect()
        self.assertEqual(result["adversarial_cases"],364)
        self.assertGreaterEqual(result["source_files"],420)
        self.assertRegex(result["sha256"],r"^[0-9a-f]{64}$")
        self.assertFalse(result["release_certified"])
    def test_tree_digest_deterministic(self):
        self.assertEqual(inspect()["sha256"],inspect()["sha256"])
if __name__=="__main__":unittest.main()
