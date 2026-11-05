"""refusal_quality: 40 untrusted policy scenarios, two allowed and 38 held."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.casebook import run_family
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile

class RefusalQualityCasebookTests(unittest.TestCase):
    def test_corpus_has_complete_negative_coverage(self):
        result=run_family("refusal_quality")
        self.assertEqual(result["family"],"refusal_quality")
        self.assertEqual(result["cases"],40)
        self.assertEqual(result["admitted"],2)
        self.assertEqual(result["rejected"],38)
        self.assertFalse(result["real_native_inference"])
        self.assertFalse(result["release_certified"])

    def test_identity(self):
        self.assertEqual(read_profile("refusal_quality").name,"refusal_quality")

if __name__=="__main__":
    unittest.main()
