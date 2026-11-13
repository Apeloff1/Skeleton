"""Focused runtime reliability flow checks; not real GGUF inference evidence."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.privacy import PrivateMetrics
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class PrivacyCases(unittest.TestCase):
    def test_private_prompt_and_bearer_are_not_retained(self):
        metric=PrivateMetrics(maximum=1)
        row=metric.observe({"status":"ok","prompt":"private data","bearer":"SECRET"},outcome="ok")
        self.assertEqual(row["input_fields_persisted"],0)
        self.assertEqual(metric.snapshot()["private_tokens_retained"],0)
        with self.assertRaises(Rejected):
            metric.observe({"status":"ok"},outcome="ok")
    def test_unknown_outcome_refused(self):
        with self.assertRaises(Rejected):
            PrivateMetrics().observe({"status":"ok"},outcome="unknown")
if __name__=="__main__":unittest.main()
