"""embedding_search: 40 strict source profile scenarios."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.casebook import run_family
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile

class EmbeddingSearchCasebookTests(unittest.TestCase):
    def test_two_accepts_and_thirty_eight_denials(self):
        result=run_family("embedding_search")
        self.assertEqual(result["family"],"embedding_search")
        self.assertEqual(result["cases"],40)
        self.assertEqual(result["admitted"],2)
        self.assertEqual(result["rejected"],38)
        self.assertFalse(result["real_native_inference"])
        self.assertFalse(result["release_certified"])

    def test_exact_identity(self):
        self.assertEqual(read_profile("embedding_search").name,"embedding_search")

if __name__=="__main__":
    unittest.main()
