"""Offline laptop runtime qualification: source_manifest; test-double only, not real native E2E."""
import unittest
from skeleton.ai.runtime.operational_ai.laptop_runtime.source_manifest import inventory
class TestSourceManifest(unittest.TestCase):
    def test_complete_executable_source_inventory(self):
        record=inventory()
        self.assertTrue(record["complete"])
        self.assertGreaterEqual(len(record["modules"]),30)
        self.assertTrue(all(x["bytes"]>0 and len(x["sha256"])==64
                            for x in record["modules"]))
        self.assertFalse(record["release_certified"])
        self.assertFalse(record["real_model_weight_present"])
    def test_digest_inventory_is_deterministic(self):
        self.assertEqual(inventory(),inventory())

if __name__=="__main__":
    unittest.main()
