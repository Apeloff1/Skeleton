"""boot_sequence: 40 finite source-policy fixtures and exact family binding."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.casebook import run_family
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile

class BootSequenceCasebookTests(unittest.TestCase):
    def test_two_approved_and_thirty_eight_held(self):
        result=run_family("boot_sequence")
        self.assertEqual(result["family"],"boot_sequence")
        self.assertEqual(result["cases"],40)
        self.assertEqual(result["admitted"],2)
        self.assertEqual(result["rejected"],38)
        self.assertFalse(result["real_native_inference"])
        self.assertFalse(result["release_certified"])

    def test_identity(self):
        self.assertEqual(read_profile("boot_sequence").name,"boot_sequence")

if __name__=="__main__":
    unittest.main()
