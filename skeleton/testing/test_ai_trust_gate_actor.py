"""Positive and malicious fixture execution for the actor AI trust boundary."""
import unittest
from skeleton.ai.runtime.operational_ai.trust_gates.fixtures import run_domain

class ActorGateTest(unittest.TestCase):
    def test_all_source_fixtures(self):
        result=run_domain("actor")
        self.assertEqual(result["status"],"contract-fixtures-passed")
        self.assertEqual((result["accepted"],result["rejected"]),(2,10))

if __name__=="__main__":
    unittest.main()
