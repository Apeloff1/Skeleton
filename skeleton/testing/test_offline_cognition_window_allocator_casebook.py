"""window_allocator: run all source-controlled bounded policy mutations."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.casebook import run_family
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile

class WindowAllocatorSourceCases(unittest.TestCase):
    def test_two_valid_and_thirty_eight_denied(self):
        report=run_family("window_allocator")
        self.assertEqual(report["family"],"window_allocator")
        self.assertEqual(report["cases"],40)
        self.assertEqual(report["admitted"],2)
        self.assertEqual(report["rejected"],38)
        self.assertFalse(report["real_native_inference"])
        self.assertFalse(report["release_certified"])

    def test_source_profile_name(self):
        self.assertEqual(read_profile("window_allocator").name,"window_allocator")

if __name__=="__main__":
    unittest.main()
