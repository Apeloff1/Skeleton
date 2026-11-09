import unittest
from skeleton.ai.assurance.disaster_recovery import DisasterRecoveryPlan
D="a"*64

class TestDisasterRecovery(unittest.TestCase):
    def test_rpo_rto_budgets_are_non_compensable(self):
        plan=DisasterRecoveryPlan("dr",1000,5000,("restore","replay","verify"),D)
        self.assertTrue(plan.meets(900,4000))
        self.assertFalse(plan.meets(1200,4000))
        self.assertFalse(plan.meets(900,6000))

if __name__=="__main__": unittest.main()
