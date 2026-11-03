"""Focused operational AI reliability test: privacy. No synthetic native E2E claim."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.privacy import PrivateMetrics
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class PrivacyTests(unittest.TestCase):
    def test_private_user_data_is_not_retained(self):
        metrics=PrivateMetrics(maximum=1)
        received=metrics.observe({"status":"ok","prompt":"SECRET","bearer":"TOKEN"},
                                  outcome="ok")
        self.assertEqual(received["input_fields_persisted"],0)
        self.assertEqual(metrics.snapshot()["raw_prompt_bytes_retained"],0)
        with self.assertRaises(Rejected):
            metrics.observe({"status":"ok"},outcome="ok")
    def test_unknown_outcome_never_counts(self):
        with self.assertRaises(Rejected):
            PrivateMetrics().observe({"status":"ok"},outcome="dangerous")

if __name__=="__main__":
    unittest.main()
