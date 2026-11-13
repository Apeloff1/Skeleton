"""Source-backed typed request and adversarial denials for privacy."""
import unittest
from skeleton.ai.runtime.operational_ai.laptop_runtime.qualification.runner import run_domain

class PrivacyQualification(unittest.TestCase):
    def test_all_fourteen_real_python_source_cases(self):
        record=run_domain("privacy")
        self.assertEqual(record["cases"],14)
        self.assertEqual((record["accepted"],record["rejected"],record["redacted"]),
                         (1,2,11))
    def test_fixture_accounting_is_deterministic(self):
        self.assertEqual(run_domain("privacy"),run_domain("privacy"))

if __name__=="__main__":
    unittest.main()
