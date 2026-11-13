"""Twelve real policy executions for cancel: two accepts, ten adversarial denials."""
import unittest
from skeleton.ai.runtime.operational_ai.trust_gates.fixtures import run_domain

class CancelGateTest(unittest.TestCase):
    def test_complete_boundary_fixture_corpus(self):
        result=run_domain("cancel")
        self.assertEqual(result["status"],"contract-fixtures-passed")
        self.assertEqual((result["accepted"],result["rejected"]),(2,10))

if __name__=="__main__": unittest.main()
