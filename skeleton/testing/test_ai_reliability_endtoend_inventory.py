"""Exact committed corpus census; native E2E qualification remains independent."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.source_inventory import inventory
from skeleton.ai.runtime.operational_ai.reliability_fabric.catalog import domains

class SourceInventoryTests(unittest.TestCase):
    def test_all_forty_executable_domains_have_complete_fixtures(self):
        item=inventory()
        self.assertEqual(item["domains"],40)
        self.assertEqual(item["source_files"],1080)
        self.assertEqual(item["cases"],880)
        self.assertFalse(item["native_model_tested"])
    def test_corpus_hash_is_deterministic(self):
        self.assertEqual(inventory()["sha256"],inventory()["sha256"])
    def test_registry_is_unique(self):
        self.assertEqual(len(domains()),len(set(domains())))
if __name__=="__main__":unittest.main()
