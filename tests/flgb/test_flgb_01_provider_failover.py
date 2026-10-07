import unittest
from skeleton.inference.provider_failover import FailoverAttempt, ProviderCandidate, ProviderFailoverPlan
class TestProviderFailover(unittest.TestCase):
    def test_ordered_bounded_failover(self):
        plan = ProviderFailoverPlan([ProviderCandidate("b","m",2), ProviderCandidate("a","m",1)])
        self.assertEqual(plan.choose([]).provider, "a")
        self.assertEqual(plan.choose([FailoverAttempt(0,"a","m","timeout")]).provider, "b")
        self.assertIsNone(plan.choose([FailoverAttempt(0,"a","m","policy_denied")]))
if __name__ == "__main__": unittest.main()
